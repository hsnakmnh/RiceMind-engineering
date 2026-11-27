#!/usr/bin/env python3
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""Build the RiceMind gene master from the current server reference layout.

Python 3.8+, standard library only. Reads TSV by header (including quoted
multiline cells), retains Oryzabase entries without RAP IDs and supplementary
IDs, and writes candidate indexes without silently choosing ambiguous aliases.
This constructs reference entries; it does not establish biological accuracy.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ricemind_config import BASE_DIR, DATA_DIR, OGER_DICT_DIR, SEQUENCE_DATA_DIR, STANDARD_GENE_DIR, SUPP_DICT_DIR
from build_dataset.build_rice_multi_omics import split_aliases

RAP_PATTERN = re.compile(r'\bOs\d{2}g\d{7}\b')
PLACEHOLDERS = {'', '_', '-', 'unknown', 'none', 'nan'}
LIST_IDS = ('Oryzabase_ID', 'Supplementary_ID', 'MSU_ID', 'Ensembl_ID', 'Gramene_ID',
            'Protein_ID', 'Transcript_ID', 'External_ID')


def first_existing(paths):
    return next((Path(p) for p in paths if Path(p).is_file()), Path(paths[0]))


def discover_files():
    reference = SEQUENCE_DATA_DIR / 'reference'
    manifest_path = reference / 'reference_manifest.json'
    oryza = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        filename = manifest.get('files', {}).get('oryzabase_utf8', {}).get('filename')
        if filename:
            if Path(filename).name != filename:
                raise ValueError('Reference manifest filenames must be basename-only')
            oryza = reference / filename
    if oryza is None:
        oryza = STANDARD_GENE_DIR / 'OryzabaseGeneListEn_20250702010110.txt'
    explicit_supp = os.environ.get('RICEMIND_SUPP_DICT_DIR') or os.environ.get('RICEMIND_OGER_GENE_DIR')
    supp = (Path(explicit_supp) / 'supplementary_gene_oger_dict.tsv' if explicit_supp else first_existing([
        OGER_DICT_DIR / 'genes/supplementary_gene_oger_dict.tsv',
        BASE_DIR / 'dict-dir/oger/genes/supplementary_gene_oger_dict.tsv',
        OGER_DICT_DIR / 'supplementary_gene_oger_dict.tsv',
        SUPP_DICT_DIR / 'supplementary_gene_oger_dict.tsv']))
    return {
        'omics_json': os.environ.get('RICEMIND_MULTI_OMICS_FILE') or str(first_existing([
            SEQUENCE_DATA_DIR / 'rice_multi_omics.json', DATA_DIR / 'rice_multi_omics.json'])),
        'oryzabase_txt': os.environ.get('RICEMIND_ORYZABASE_FILE') or str(oryza),
        'planteome_txt': os.environ.get('RICEMIND_PROTEIN_GENE_MAPPING_FILE') or str(first_existing([
            BASE_DIR / 'asset/protein_gene_mapping.txt', STANDARD_GENE_DIR / 'protein_gene_mapping.txt'])),
        'supp_dict_tsv': str(supp),
        'output_json': str(STANDARD_GENE_DIR / 'Unified_Gene_Master.json'),
    }


# Retain the existing diagnostic import contract: from ... import FILES.
FILES = discover_files()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def create_empty_entry(rap_id_val=None):
    return {
        'IDs': dict({'RAP_ID': rap_id_val}, **{key: [] for key in LIST_IDS}),
        'Nomenclature': {'Primary_Symbol': '', 'All_Symbols': [], 'CGSNL_Name': '', 'All_Names': []},
        'Annotations': {'Explanation': '', 'Trait_Class': ''},
        'Location': {'Chromosome': None, 'Start': None, 'End': None, 'Strand': None},
        'External_Links': {}, 'External_Identifiers': {}, 'Sources': [],
    }


def add_values(target, values):
    for value in values:
        value = str(value).strip()
        if value and value not in target:
            target.append(value)


def add_names(target, symbols=(), names=(), primary='', official_name=''):
    nomenclature = target['Nomenclature']
    add_values(nomenclature['All_Symbols'], symbols)
    add_values(nomenclature['All_Names'], names)
    if primary and not nomenclature['Primary_Symbol']:
        nomenclature['Primary_Symbol'] = primary
    if official_name and not nomenclature['CGSNL_Name']:
        nomenclature['CGSNL_Name'] = official_name


def validate_inputs(files):
    for role in ('omics_json', 'oryzabase_txt', 'planteome_txt', 'supp_dict_tsv'):
        path = Path(files[role])
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError('Missing or empty input {}: {}'.format(role, path))
    # Verify upload integrity when the supporting records are present.
    oryza = Path(files['oryzabase_txt'])
    manifest_path = oryza.parent / 'reference_manifest.json'
    if manifest_path.is_file():
        record = json.loads(manifest_path.read_text(encoding='utf-8')).get('files', {}).get('oryzabase_utf8', {})
        if record.get('filename') == oryza.name and file_hash(oryza) != record['sha256']:
            raise ValueError('Oryzabase upload does not match reference manifest')
    omics = Path(files['omics_json'])
    build_report = omics.with_name(omics.stem + '_build_report.json')
    if build_report.is_file():
        recorded = json.loads(build_report.read_text(encoding='utf-8')).get('output_sha256')
        if recorded and file_hash(omics) != recorded:
            raise ValueError('Omics JSON upload does not match its build report')


def merge_omics(path, master, counts):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    payload = data.get('gene_payload')
    if not isinstance(payload, dict) or not payload:
        raise ValueError('Omics input lacks nonempty gene_payload')
    for rap, info in payload.items():
        if not RAP_PATTERN.fullmatch(rap) or info.get('rap_id') != rap:
            raise ValueError('Invalid omics RAP ID: ' + rap)
        target = master.setdefault(rap, create_empty_entry(rap))
        location = info.get('location') or {}
        target['Location'] = {key: location.get(source) for key, source in (
            ('Chromosome', 'chromosome'), ('Start', 'start'), ('End', 'end'), ('Strand', 'strand'))}
        target['External_Links'].update(info.get('external_links') or {})
        add_values(target['IDs']['Ensembl_ID'], [rap])
        add_values(target['Sources'], ['Omics'])
        add_names(target, info.get('all_symbols') or [], info.get('all_names') or [], info.get('primary_symbol', ''))
        for transcript in info.get('transcripts') or []:
            add_values(target['IDs']['Transcript_ID'], [transcript.get('transcript_id', '')])
            if transcript.get('protein_seq') is not None:
                add_values(target['IDs']['Protein_ID'], [transcript.get('protein_id', '')])
    counts['omics_gene_entries'] = len(payload)
    return data.get('metadata') or {}


def merge_oryzabase(path, master, counts):
    required = {'CGSNL Gene Symbol', 'Gene symbol synonym(s)', 'CGSNL Gene Name',
                'Gene name synonym(s)', 'Explanation', 'Trait Class', 'RAP ID', 'MSU ID'}
    seen = set()
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        columns = set(reader.fieldnames or [])
        if not required <= columns:
            raise ValueError('Missing Oryzabase columns: ' + repr(sorted(required - columns)))
        id_col = next((c for c in ('Trait Gene Id', 'Trait Gene ID', 'Trait Id', 'Trait ID') if c in columns), None)
        gramene_col = next((c for c in ('Gramene ID', 'GrameneId') if c in columns), None)
        if not id_col:
            raise ValueError('Oryzabase export has no gene ID column')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed Oryzabase record near line ' + str(reader.line_num))
            raw_id = row[id_col].strip()
            if not raw_id or raw_id in seen:
                raise ValueError('Empty or duplicated Oryzabase gene ID: ' + raw_id)
            seen.add(raw_id)
            counts['oryzabase_records'] += 1
            original_id = raw_id if raw_id.startswith('OryzaGeneID:') else 'OryzaGeneID:' + raw_id
            raps = sorted(set(RAP_PATTERN.findall(row['RAP ID'])))
            if row['RAP ID'].strip() and not raps:
                counts['oryzabase_nonstandard_rap_cells'] += 1
            counts['oryzabase_records_with_multiple_raps'] += len(raps) > 1
            if not raps:
                counts['oryzabase_records_without_rap'] += 1
            for key in raps or [original_id]:
                rap = key if RAP_PATTERN.fullmatch(key) else None
                target = master.setdefault(key, create_empty_entry(rap))
                add_values(target['Sources'], ['Oryzabase'])
                add_values(target['IDs']['Oryzabase_ID'], [original_id])
                add_values(target['IDs']['MSU_ID'], split_aliases(row['MSU ID']))
                if gramene_col:
                    add_values(target['IDs']['Gramene_ID'], split_aliases(row[gramene_col]))
                symbol, name = row['CGSNL Gene Symbol'].strip(), row['CGSNL Gene Name'].strip()
                add_names(target, [symbol] + split_aliases(row['Gene symbol synonym(s)']),
                          [name] + split_aliases(row['Gene name synonym(s)']), symbol, name)
                for field, column in (('Explanation', 'Explanation'), ('Trait_Class', 'Trait Class')):
                    value = row[column].strip()
                    if value and not target['Annotations'][field]:
                        target['Annotations'][field] = value
    if not counts['oryzabase_records']:
        raise ValueError('Oryzabase export has no records')


def merge_external_mapping(path, master, counts):
    required = {'RAP_ID', 'External_Source', 'Protein_or_Transcript_ID'}
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if not required <= set(reader.fieldnames or []):
            raise ValueError('Mapping table lacks required columns')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed mapping record near line ' + str(reader.line_num))
            counts['external_mapping_records'] += 1
            rap, source, external_id = (row[column].strip() for column in ('RAP_ID', 'External_Source', 'Protein_or_Transcript_ID'))
            if rap not in master or not external_id:
                counts['external_mapping_records_not_in_master'] += 1
                continue
            target = master[rap]
            add_values(target['External_Identifiers'].setdefault(source, []), [external_id])
            add_values(target['Sources'], ['ExternalMapping'])
            if source.casefold() == 'protein_id' or source.casefold().startswith('uniprot/'):
                add_values(target['IDs']['Protein_ID'], [external_id])
            else:
                # Preserve EMBL sequence accessions without falsely labelling all as proteins.
                add_values(target['IDs']['External_ID'], [external_id])
            counts['external_mapping_records_attached'] += 1
    if not counts['external_mapping_records']:
        raise ValueError('Mapping table has no records')


def merge_supplementary(path, master, counts):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if not row or not any(row) or row[0].lstrip().startswith('#'):
                continue
            if len(row) != 6 or row[5].strip().casefold() != 'gene' or not row[2].startswith('Supplementary_geneID:'):
                raise ValueError('Unexpected supplementary dictionary row near line ' + str(reader.line_num))
            counts['supplementary_dictionary_rows'] += 1
            key, term, standard = row[2].strip(), row[3].strip(), row[4].strip()
            target = master.setdefault(key, create_empty_entry())
            add_values(target['Sources'], ['Supplementary'])
            add_values(target['IDs']['Supplementary_ID'], [key])
            add_names(target, [term, standard], primary=standard or term)
    if not counts['supplementary_dictionary_rows']:
        raise ValueError('Supplementary dictionary has no records')


def candidate_indexes(master):
    ids, symbols = defaultdict(set), defaultdict(set)
    for key, info in master.items():
        ids[key.casefold()].add(key)
        for value in info['IDs'].values():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item:
                    ids[str(item).strip().casefold()].add(key)
        for name in info['Nomenclature']['All_Symbols']:
            alias = name.strip().casefold()
            if alias not in PLACEHOLDERS:
                symbols[alias].add(key)
    return {'id_candidates': {k: sorted(v) for k, v in sorted(ids.items())},
            'symbol_candidates': {k: sorted(v) for k, v in sorted(symbols.items())}}


def collect_master(files):
    validate_inputs(files)
    counts, master = Counter(), {}
    metadata = merge_omics(files['omics_json'], master, counts)
    merge_oryzabase(files['oryzabase_txt'], master, counts)
    merge_external_mapping(files['planteome_txt'], master, counts)
    merge_supplementary(files['supp_dict_tsv'], master, counts)
    for info in master.values():
        for field in LIST_IDS:
            info['IDs'][field].sort()
        for field in ('All_Symbols', 'All_Names'):
            info['Nomenclature'][field].sort()
        info['Sources'].sort()
        for values in info['External_Identifiers'].values():
            values.sort()
    master = dict(sorted(master.items()))
    indexes = candidate_indexes(master)
    counts.update(total_entries=len(master),
                  rap_entries=sum(bool(info['IDs']['RAP_ID']) for info in master.values()),
                  oryzabase_entries_without_rap=sum(key.startswith('OryzaGeneID:') for key in master),
                  supplementary_entries=sum(key.startswith('Supplementary_geneID:') for key in master),
                  ambiguous_id_aliases=sum(len(v) > 1 for v in indexes['id_candidates'].values()),
                  ambiguous_symbol_aliases=sum(len(v) > 1 for v in indexes['symbol_candidates'].values()))
    report = dict(counts=dict(counts), omics_metadata=metadata,
        inputs={role: {'path': str(Path(files[role]).resolve()), 'size_bytes': Path(files[role]).stat().st_size,
                       'sha256': file_hash(files[role])} for role in ('omics_json', 'oryzabase_txt', 'planteome_txt', 'supp_dict_tsv')},
        notes=['Counts describe reference entries, not independently validated biological gene counts.',
               'No supplementary gene was merged into a canonical RAP entry solely by name.',
               'Aliases with multiple candidates require resolution in the downstream association stage.',
               'EMBL sequence accessions are retained as external IDs rather than all labelled proteins.'])
    return master, indexes, report


def atomic_json(path, data):
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for flag, role in (('--omics-json', 'omics_json'), ('--oryzabase-file', 'oryzabase_txt'),
                       ('--protein-mapping', 'planteome_txt'), ('--supp-dict', 'supp_dict_tsv')):
        p.add_argument(flag, dest=role, type=Path, default=Path(FILES[role]))
    p.add_argument('--output-dir', type=Path, default=STANDARD_GENE_DIR)
    p.add_argument('--check-only', action='store_true', help='Validate and assemble in memory, without writing outputs')
    p.add_argument('--force', action='store_true', help='Explicitly replace existing generated outputs')
    args = p.parse_args(argv)
    files = {role: str(getattr(args, role)) for role in ('omics_json', 'oryzabase_txt', 'planteome_txt', 'supp_dict_tsv')}
    outputs = [args.output_dir / name for name in (
        'Unified_Gene_Master.json', 'Unified_Gene_Alias_Index.json', 'Unified_Gene_Master_build_report.json')]
    for output in outputs:
        if output.resolve() in {Path(value).resolve() for value in files.values()}:
            raise ValueError('Output would overwrite an input: ' + str(output))
        if output.exists() and not args.force and not args.check_only:
            raise ValueError('Output exists; use a new --output-dir or explicitly --force: ' + str(output))
    for role, value in files.items():
        print('[INPUT] {}: {}'.format(role, value), flush=True)
    master, indexes, report = collect_master(files)
    counts = report['counts']
    print('[SUMMARY] total={:,}; RAP={:,}; Oryzabase without RAP={:,}; supplementary={:,}'.format(
        counts['total_entries'], counts['rap_entries'], counts['oryzabase_entries_without_rap'],
        counts['supplementary_entries']), flush=True)
    print('[SUMMARY] ambiguous ID aliases={:,}; ambiguous symbol aliases={:,}'.format(
        counts['ambiguous_id_aliases'], counts['ambiguous_symbol_aliases']), flush=True)
    if args.check_only:
        print('[CHECK] Passed; no output files written.', flush=True)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat())
    atomic_json(outputs[0], master)
    atomic_json(outputs[1], indexes)
    report['outputs'] = {path.name: {'sha256': file_hash(path), 'size_bytes': path.stat().st_size} for path in outputs[:2]}
    atomic_json(outputs[2], report)
    for output in outputs:
        print('[OUTPUT] ' + str(output.resolve()), flush=True)
    return 0


# Keep the original callable entry point for older wrappers.
def build_universal_gene_master():
    return main([])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(2)
