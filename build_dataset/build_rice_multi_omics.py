#!/usr/bin/env python3
"""Build rice_multi_omics.json from the downloaded reference manifest.

Python 3.8+ standard library only. Keeps the original RiceMind gene_payload /
search_index schema. Processes FASTA chromosome by chromosome, validates GFF3
coordinates, and links proteins by transcript metadata rather than assuming
that protein record IDs must equal cDNA IDs. Never rewrites annotation results.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
RAP_RE = re.compile(r'\bOs\d{2}g\d{7}\b')
COMPLEMENT = str.maketrans('ACGTRYKMSWBDHVNacgtrykmswbdhvn', 'TGCAYRMKSWVHDBNtgcayrmkswvhdbn')
ROLES = ('oryzabase_utf8', 'gff3', 'dna', 'cdna', 'pep')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def split_aliases(value):
    """Split top-level comma/pipe lists; preserve semicolons, slashes and brackets."""
    parts, current, depth = [], [], 0
    for char in value:
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth = max(0, depth - 1)
        if char in ',|' and depth == 0:
            term = ''.join(current).strip()
            if term:
                parts.append(term)
            current = []
        else:
            current.append(char)
    term = ''.join(current).strip()
    if term:
        parts.append(term)
    return parts


def read_oryzabase(path):
    genes, symbols, names = {}, defaultdict(set), defaultdict(set)
    stats = Counter()
    required = {'RAP ID', 'CGSNL Gene Symbol', 'CGSNL Gene Name',
                'Gene symbol synonym(s)', 'Gene name synonym(s)'}
    with path.open(encoding='utf-8-sig', newline='') as f:
        # The official export quotes embedded tabs/newlines; use a real TSV reader.
        reader = csv.DictReader(f, delimiter='\t')
        if not required <= set(reader.fieldnames or []):
            raise ValueError('Missing Oryzabase columns: ' + repr(sorted(required - set(reader.fieldnames or []))))
        id_column = next((c for c in ('Trait Gene Id', 'Trait Gene ID', 'Trait Id', 'Trait ID')
                          if c in reader.fieldnames), None)
        if id_column is None:
            raise ValueError('Oryzabase export lacks an identifiable gene ID column')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed Oryzabase row at line ' + str(reader.line_num))
            stats['oryzabase_rows'] += 1
            raps = sorted(set(RAP_RE.findall(row['RAP ID'])))
            if not raps:
                stats['oryzabase_rows_without_rap'] += 1
                continue
            stats['oryzabase_rows_with_rap'] += 1
            stats['oryzabase_rows_with_multiple_raps'] += len(raps) > 1
            for rap in raps:
                if rap not in genes:
                    genes[rap] = dict(rap_id=rap, primary_symbol='', all_symbols=[], all_names=[],
                        oryzabase_ids=[], raw_nomenclature=[], location=None, genomic_seq=None, transcripts=[],
                        external_links={
                            'RAP-DB': 'https://rapdb.dna.naro.go.jp/search/?q=' + rap,
                            'Ensembl_Plants': 'https://plants.ensembl.org/Oryza_sativa/Gene/Summary?g=' + rap,
                            'Gramene': 'https://ensembl.gramene.org/Oryza_sativa/Gene/Summary?g=' + rap})
                gene = genes[rap]
                symbol, name = row['CGSNL Gene Symbol'].strip(), row['CGSNL Gene Name'].strip()
                if symbol and not gene['primary_symbol']:
                    gene['primary_symbol'] = symbol
                if symbol:
                    symbols[rap].add(symbol)
                if name:
                    names[rap].add(name)
                symbols[rap].update(split_aliases(row['Gene symbol synonym(s)']))
                names[rap].update(split_aliases(row['Gene name synonym(s)']))
                source_id = row[id_column].strip()
                if source_id and source_id not in gene['oryzabase_ids']:
                    gene['oryzabase_ids'].append(source_id)
                gene['raw_nomenclature'].append({key: row[key] for key in (id_column, 'CGSNL Gene Symbol',
                    'Gene symbol synonym(s)', 'CGSNL Gene Name', 'Gene name synonym(s)', 'RAP ID')})
    if not genes:
        raise ValueError('No recognizable RAP IDs in Oryzabase input')
    for rap, gene in genes.items():
        gene['all_symbols'], gene['all_names'] = sorted(symbols[rap]), sorted(names[rap])
    stats['oryzabase_distinct_rap_ids'] = len(genes)
    return genes, stats


def attributes(text):
    return {key: unquote(value) for item in text.split(';') if '=' in item
            for key, value in [item.split('=', 1)]}


def strip_prefix(value):
    return value.split(':', 1)[-1]


def read_gff3(path, genes, stats):
    transcript_gene, protein_transcript = {}, {}
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for number, line in enumerate(f, 1):
            if line.startswith('#') or not line.strip():
                continue
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) != 9:
                raise ValueError('Malformed GFF3 line ' + str(number))
            attr = attributes(fields[8])
            if fields[2] == 'gene':
                stats['gff3_gene_features'] += 1
                rap = attr.get('gene_id') or strip_prefix(attr.get('ID', ''))
                if rap not in genes:
                    continue
                start, end, strand = int(fields[3]), int(fields[4]), fields[6]
                if start < 1 or end < start or strand not in ('+', '-'):
                    raise ValueError('Invalid gene coordinates: ' + rap)
                location = dict(chromosome=fields[0], start=start, end=end, strand=strand)
                prior = genes[rap]['location']
                if prior and prior != location:
                    raise ValueError('Conflicting locations for ' + rap)
                genes[rap]['location'] = location
            elif attr.get('Parent', '').startswith('gene:'):
                tid = attr.get('transcript_id') or strip_prefix(attr.get('ID', ''))
                gid = strip_prefix(attr['Parent'])
                if tid:
                    prior = transcript_gene.get(tid)
                    if prior and prior != gid:
                        raise ValueError('Transcript assigned to different genes: ' + tid)
                    transcript_gene[tid] = gid
            if fields[2] == 'CDS' and attr.get('protein_id'):
                tid = strip_prefix(attr.get('Parent', ''))
                if tid:
                    pid = attr['protein_id']
                    if pid in protein_transcript and protein_transcript[pid] != tid:
                        raise ValueError('Protein assigned to different transcripts: ' + pid)
                    protein_transcript[pid] = tid
    stats['genes_with_gff3_coordinates'] = sum(g['location'] is not None for g in genes.values())
    if not stats['genes_with_gff3_coordinates']:
        raise ValueError('No Oryzabase RAP IDs matched the GFF3 gene features')
    return transcript_gene, protein_transcript


def fasta_records(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        header, chunks = None, []
        for number, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith('>'):
                if header is not None:
                    sequence = ''.join(chunks)
                    if not sequence:
                        raise ValueError('Empty FASTA record: ' + header)
                    yield header, sequence
                header, chunks = line[1:], []
            else:
                if header is None:
                    raise ValueError('FASTA sequence before first header at line ' + str(number))
                chunks.append(line)
        if header is not None:
            sequence = ''.join(chunks)
            if not sequence:
                raise ValueError('Empty FASTA record: ' + header)
            yield header, sequence


def header_value(header, key):
    m = re.search(r'(?:^|\s)' + re.escape(key) + r':([^\s]+)', header)
    return m.group(1) if m else ''


def add_dna(path, genes, stats):
    by_chromosome, seen = defaultdict(list), set()
    for rap, gene in genes.items():
        if gene['location']:
            by_chromosome[gene['location']['chromosome']].append(rap)
    for header, sequence in fasta_records(path):
        chromosome = header.split()[0]
        if chromosome in seen:
            raise ValueError('Duplicate DNA FASTA record: ' + chromosome)
        seen.add(chromosome)
        for rap in by_chromosome.get(chromosome, []):
            loc = genes[rap]['location']
            if loc['end'] > len(sequence):
                raise ValueError('Gene coordinate exceeds chromosome length: ' + rap)
            dna = sequence[loc['start'] - 1:loc['end']]
            genes[rap]['genomic_seq'] = dna.translate(COMPLEMENT)[::-1] if loc['strand'] == '-' else dna
    stats['genes_with_dna'] = sum(g['genomic_seq'] is not None for g in genes.values())
    stats['genes_with_coordinates_but_no_dna'] = sum(g['location'] is not None and g['genomic_seq'] is None for g in genes.values())
    if stats['genes_with_coordinates_but_no_dna']:
        raise ValueError('GFF3 chromosome names did not match DNA FASTA')
    if not stats['genes_with_dna']:
        raise ValueError('No genomic DNA sequences extracted')


def add_transcripts(cdna, pep, genes, transcript_gene, protein_transcript, stats):
    lookup = {}
    for header, sequence in fasta_records(cdna):
        stats['cdna_records_read'] += 1
        tid = header_value(header, 'transcript') or header.split()[0]
        gene_id = header_value(header, 'gene') or transcript_gene.get(tid, '')
        if gene_id not in genes:
            continue
        if tid in lookup:
            raise ValueError('Duplicate cDNA transcript ID: ' + tid)
        item = dict(transcript_id=tid, cdna_seq=sequence, protein_seq=None, protein_id=None)
        genes[gene_id]['transcripts'].append(item)
        lookup[tid] = (gene_id, item)
        stats['cdna_records_attached'] += 1
    for header, sequence in fasta_records(pep):
        stats['protein_records_read'] += 1
        pid = header.split()[0]
        tid = header_value(header, 'transcript') or protein_transcript.get(pid, pid)
        gene_id = header_value(header, 'gene') or transcript_gene.get(tid, '')
        if gene_id not in genes:
            continue
        if tid not in lookup:
            stats['selected_gene_proteins_without_cdna'] += 1
            continue
        actual_gene, item = lookup[tid]
        if actual_gene != gene_id:
            raise ValueError('Protein/cDNA gene mismatch: ' + pid)
        if item['protein_seq'] is not None:
            raise ValueError('Multiple protein records for transcript ' + tid)
        item.update(protein_seq=sequence, protein_id=pid)
        stats['protein_records_attached'] += 1
    stats['genes_with_cdna'] = sum(bool(g['transcripts']) for g in genes.values())
    stats['genes_with_protein'] = sum(any(t['protein_seq'] is not None for t in g['transcripts']) for g in genes.values())
    if not stats['cdna_records_attached'] or not stats['protein_records_attached']:
        raise ValueError('No cDNA/protein attachments; verify reference identifiers and version')


def make_index(genes):
    index = defaultdict(set)
    for rap, gene in genes.items():
        for term in [rap] + gene['all_symbols'] + gene['all_names']:
            key = term.casefold().replace('[', '').replace(']', '').strip()
            if key:
                index[key].add(rap)
    return {key: sorted(value) for key, value in sorted(index.items())}


def build(oryzabase, gff3, dna, cdna, pep):
    genes, stats = read_oryzabase(oryzabase)
    print('[BUILD] Oryzabase RAP IDs: {:,}'.format(len(genes)), flush=True)
    tids, pids = read_gff3(gff3, genes, stats)
    print('[BUILD] GFF3 matched genes: {:,}'.format(stats['genes_with_gff3_coordinates']), flush=True)
    add_dna(dna, genes, stats)
    print('[BUILD] Genes with DNA: {:,}'.format(stats['genes_with_dna']), flush=True)
    add_transcripts(cdna, pep, genes, tids, pids, stats)
    without_sequence = sorted(rap for rap, g in genes.items() if g['genomic_seq'] is None and not g['transcripts'])
    # Same sequence-backed scope as the original script; exclusions remain in the report.
    excluded_set = set(without_sequence)
    genes = {rap: gene for rap, gene in genes.items() if rap not in excluded_set}
    stats['genes_without_sequence_excluded'] = len(without_sequence)
    stats['output_gene_count'] = len(genes)
    index = make_index(genes)
    stats['index_term_count'] = len(index)
    stats['ambiguous_index_terms'] = sum(len(value) > 1 for value in index.values())
    return dict(search_index=index, gene_payload=genes), dict(counts=dict(stats), excluded_rap_ids=without_sequence)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=ROOT / 'sequence_data' / 'reference')
    p.add_argument('--manifest', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--force', action='store_true', help='Replace existing generated output explicitly')
    args = p.parse_args()
    folder = args.data_dir.resolve()
    manifest_path = args.manifest or folder / 'reference_manifest.json'
    output = args.output or ROOT / 'sequence_data' / 'rice_multi_omics.json'
    report_path = output.with_name(output.stem + '_build_report.json')
    if (output.exists() or report_path.exists()) and not args.force:
        raise ValueError('Output already exists; use another --output or explicitly --force')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('status') != 'complete':
        raise ValueError('Reference downloads are incomplete; finish the downloader first')
    files = {}
    for role in ROLES:
        record = manifest['files'][role]
        filename = record['filename']
        if Path(filename).name != filename:
            raise ValueError('Manifest filenames must be basename-only')
        path = folder / filename
        if not path.is_file() or sha256(path) != record['sha256']:
            raise ValueError('Missing or changed reference: ' + str(path))
        files[role] = path
    result, report = build(files['oryzabase_utf8'], files['gff3'], files['dna'], files['cdna'], files['pep'])
    metadata = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), assembly=manifest['assembly'],
        ensembl_release=manifest['ensembl_release'], oryzabase_file=manifest['files']['oryzabase_raw']['filename'],
        reference_manifest_sha256=sha256(manifest_path),
        gene_scope='Oryzabase RAP IDs with DNA or cDNA; matches the original sequence-backed scope',
        notes=['Current Oryzabase export differs from the author\'s 2025 snapshot.',
               'This reference dataset does not change existing literature annotations.',
               'Aliases may map to multiple RAP IDs; the search index preserves these alternatives.'])
    result['metadata'] = metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, result)
    report.update(metadata=metadata, output_sha256=sha256(output), output_size_bytes=output.stat().st_size,
                  inputs={role: dict(manifest['files'][role]) for role in ROLES})
    atomic_json(report_path, report)
    print('[COMPLETE] Genes: {:,}; transcripts: {:,}; proteins: {:,}'.format(
        report['counts']['output_gene_count'], report['counts']['cdna_records_attached'],
        report['counts']['protein_records_attached']), flush=True)
    print('[OUTPUT] ' + str(output), flush=True)
    print('[REPORT] ' + str(report_path), flush=True)

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, UnicodeError, EOFError) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(2)
