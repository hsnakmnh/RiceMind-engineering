#!/usr/bin/env python3
"""Prepare review tables from a completed association batch (Python 3.8+).

Uses only the standard library. Does not change source annotations or rules.
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

RAP = re.compile(r'Os\d{2}g\d{7}')
FILES = ('normalized_sentences.jsonl', 'gene_normalization_audit.tsv',
         'NLP_Rice_GTA_Database.tsv', 'NLP_Rice_GVA_TVA_Database.tsv',
         'NLP_Rice_GTA_Trend.tsv')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def table(path, required):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        if not set(required) <= set(reader.fieldnames or []):
            raise ValueError('Missing TSV columns: ' + str(path))
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed TSV record: ' + str(path))
            yield row


def save_table(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def assert_count(name, value, expected):
    if expected.get(name) != value:
        raise ValueError('{}: observed {}, summary {}'.format(name, value, expected.get(name)))


def check_context(row, corpus):
    sid = row['Sentence_ID']
    if sid not in corpus:
        raise ValueError('Unknown Sentence_ID: ' + sid)
    original = corpus[sid]
    if row['PMID'] != str(original['PMID']) or int(row['Year']) != int(original['year']):
        raise ValueError('PMID/year mismatch: ' + sid)
    if 'Sentence_Text' in row and row['Sentence_Text'] != original['text']:
        raise ValueError('Sentence text mismatch: ' + sid)
    return original


def prepare(folder, sample_size=50, seed=20261014):
    """Validate published counts and return review materials without writing."""
    folder = Path(folder)
    summary = json.loads((folder / 'association_summary.json').read_text(encoding='utf-8'))
    if summary.get('status') != 'complete':
        raise ValueError('Select a completed association batch')
    for name in FILES:
        path = folder / name
        recorded = summary.get('outputs', {}).get(name, {})
        if not path.is_file() or not recorded.get('sha256') or digest(path) != recorded['sha256']:
            raise ValueError('Missing or changed published file: ' + str(path))
    expected = summary['counts']
    corpus, measured, excluded = {}, Counter(), Counter()
    with (folder / FILES[0]).open(encoding='utf-8') as handle:
        for line in handle:
            record = json.loads(line)
            sid = record['sent_id']
            if sid in corpus:
                raise ValueError('Duplicate normalized sentence: ' + sid)
            corpus[sid] = dict(PMID=record['PMID'], year=record['year'], text=record['text'])
            kept, removed = record['normalized_entities'], record['excluded_annotations']
            cats = {entity['cat'] for entity in kept}
            measured['input_unique_mentions'] += len(kept) + len(removed)
            measured['retained_unique_mentions'] += len(kept)
            measured['input_gene_mentions'] += sum(entity['cat'] == 'Gene' for entity in kept + removed)
            measured['retained_gene_mentions'] += sum(entity['cat'] == 'Gene' for entity in kept)
            measured['gene_sentences'] += 'Gene' in cats
            measured['gene_trait_sentences'] += {'Gene', 'Phenotype'} <= cats
            measured['multi_category_sentences'] += len(cats) >= 2
            excluded.update(entity['category'] for entity in removed)
    measured['input_sentences'] = len(corpus)
    for name in ('input_sentences', 'input_unique_mentions', 'retained_unique_mentions',
                 'input_gene_mentions', 'gene_sentences', 'gene_trait_sentences', 'multi_category_sentences'):
        assert_count(name, measured[name], expected)
    if excluded != Counter(summary['excluded_mentions_by_category']):
        raise ValueError('Excluded mention counts differ from summary')

    pending, frequencies, status_counts = [], {}, Counter()
    audit_fields = ['PMID', 'Sentence_ID', 'Year', 'Original_Gene_ID', 'Matched_Text', 'Start', 'End',
                    'Gene_Key', 'RAP_ID', 'Gene_Symbol', 'Mapping_Status', 'Candidate_Gene_Keys',
                    'Standard_Name_Candidates', 'Tools', 'Review_Flags']
    for row in table(folder / FILES[1], audit_fields):
        original = check_context(row, corpus)
        start, end = int(row['Start']), int(row['End'])
        if not (0 <= start < end <= len(original['text'])) or original['text'][start:end] != row['Matched_Text']:
            raise ValueError('Audit offsets differ from sentence: ' + row['Sentence_ID'])
        status_counts[row['Mapping_Status']] += 1
        if row['Mapping_Status'].startswith(('ambiguous_', 'unmapped_')):
            pending.append(dict({key: row[key] for key in audit_fields}, Sentence_Text=original['text'],
                                Review_Decision='', Suggested_Gene_Key='', Notes=''))
        if row['Mapping_Status'] == 'blacklisted':
            continue
        key = (row['Original_Gene_ID'], row['Matched_Text'])
        item = frequencies.setdefault(key, dict(mentions=0, sids=set(), pmids=set(), statuses=set(),
                                                raps=set(), names=set(), example_sid=row['Sentence_ID']))
        item['mentions'] += 1
        item['sids'].add(row['Sentence_ID'])
        item['pmids'].add(row['PMID'])
        item['statuses'].add(row['Mapping_Status'])
        if row['RAP_ID']:
            item['raps'].add(row['RAP_ID'])
        item['names'].update(json.loads(row['Standard_Name_Candidates']))
    if sum(status_counts.values()) != expected['input_gene_mentions']:
        raise ValueError('Gene audit row count differs from summary')
    if status_counts != Counter(summary['gene_mapping_mentions']):
        raise ValueError('Gene mapping statuses differ from summary')
    frequency_rows = []
    for (entity_id, matched), item in sorted(frequencies.items(), key=lambda kv: (-kv[1]['mentions'], kv[0])):
        frequency_rows.append(dict(Original_Gene_ID=entity_id, Matched_Text=matched,
            Mentions=item['mentions'], Sentences=len(item['sids']), Articles=len(item['pmids']),
            Mapping_Status='|'.join(sorted(item['statuses'])), RAP_IDs=json.dumps(sorted(item['raps'])),
            Standard_Name_Candidates=json.dumps(sorted(item['names']), ensure_ascii=False),
            Example_Sentence_ID=item['example_sid'], Example_Sentence_Text=corpus[item['example_sid']]['text'],
            Review_Decision='', Notes=''))

    # Reservoirs are independent, uniform samples of evidence rows within each relation type.
    rng = {kind: random.Random('{}:{}'.format(seed, kind)) for kind in ('GTA', 'GVA', 'TVA')}
    samples = {kind: [] for kind in rng}
    relation_counts, gene_keys, rap_genes, pairs, rap_pairs = Counter(), set(), set(), set(), set()
    for filename, fixed_kind in ((FILES[2], 'GTA'), (FILES[3], None)):
        required = ['PMID', 'Sentence_ID', 'Year', 'Sentence_Text', 'Gene_Key', 'Ontology_ID',
                    'Mapping_Status', 'Original_Gene_ID', 'Gene_Symbol', 'Trait_Description']
        if fixed_kind is None:
            required += ['Relation_Type', 'Variety_ID', 'Variety_Name', 'Gene_RAP_ID']
        else:
            required += ['RAP_ID']
        for row in table(folder / filename, required):
            kind = fixed_kind or row['Relation_Type']
            if kind not in rng or (fixed_kind is None and kind == 'GTA'):
                raise ValueError('Unknown relation type: ' + kind)
            check_context(row, corpus)
            relation_counts[kind] += 1
            rap = row.get('RAP_ID', row.get('Gene_RAP_ID', ''))
            if rap and not RAP.fullmatch(rap):
                raise ValueError('Invalid RAP ID: ' + rap)
            if kind == 'GTA':
                gene_keys.add(row['Gene_Key'])
                pairs.add((row['Gene_Key'], row['Ontology_ID']))
                if rap:
                    measured['gta_rows_with_rap'] += 1
                    rap_genes.add(rap)
                    rap_pairs.add((rap, row['Ontology_ID']))
            candidate = dict(Relation_Type=kind, PMID=row['PMID'], Sentence_ID=row['Sentence_ID'],
                Year=row['Year'], Gene_Key=row['Gene_Key'], RAP_ID=rap, Gene_Symbol=row['Gene_Symbol'],
                Original_Gene_ID=row['Original_Gene_ID'], Mapping_Status=row['Mapping_Status'],
                Candidate_Gene_Keys=row.get('Candidate_Gene_Keys', ''),
                Ontology_ID=row['Ontology_ID'], Trait_Description=row['Trait_Description'],
                Trait_Name_Candidates=row.get('Trait_Name_Candidates', ''),
                Variety_ID=row.get('Variety_ID', ''), Variety_Name=row.get('Variety_Name', ''),
                Variety_Name_Candidates=row.get('Variety_Name_Candidates', ''),
                Sentence_Text=row['Sentence_Text'], Gene_Correct='', Trait_Correct='',
                Variety_Correct='', Relation_Supported='', Notes='')
            sample = samples[kind]
            if len(sample) < sample_size:
                sample.append(candidate)
            else:
                index = rng[kind].randrange(relation_counts[kind])
                if index < sample_size:
                    sample[index] = candidate
    for kind in rng:
        assert_count(kind.lower() + '_rows', relation_counts[kind], expected)
    assert_count('gta_rows_with_rap', measured['gta_rows_with_rap'], expected)
    assert_count('unique_gta_pairs', len(pairs), expected)
    trend_pairs = set()
    for row in table(folder / FILES[4], ['Gene_Key', 'Ontology_ID', 'Article_Count', 'Sentence_Count']):
        pair = (row['Gene_Key'], row['Ontology_ID'])
        if pair in trend_pairs or not 1 <= int(row['Article_Count']) <= int(row['Sentence_Count']):
            raise ValueError('Invalid or repeated trend row: ' + str(pair))
        trend_pairs.add(pair)
    if trend_pairs != pairs:
        raise ValueError('Trend pairs differ from sentence-level GTA pairs')
    report = dict(status='review_materials_ready', association_dir=str(folder.resolve()),
        source_summary_sha256=digest(folder / 'association_summary.json'), validation='passed',
        counts=dict(input_sentences=len(corpus), retained_gene_mentions=measured['retained_gene_mentions'],
            gene_mapping_review_mentions=len(pending), gene_mapping_review_ids=len({r['Original_Gene_ID'] for r in pending}),
            gene_mapping_mentions=dict(status_counts), gta_rows=relation_counts['GTA'],
            gva_rows=relation_counts['GVA'], tva_rows=relation_counts['TVA'], unique_gta_pairs=len(pairs),
            gta_gene_keys=len(gene_keys), gta_rap_genes=len(rap_genes), unique_rap_gta_pairs=len(rap_pairs)),
        sampling=dict(seed=seed, requested_per_relation_type=sample_size,
            sampled_rows={kind: len(rows) for kind, rows in samples.items()},
            design='Uniform evidence-row samples separately for GTA, GVA and TVA; a sentence may appear more than once.'),
        notes=['Review decisions are blank; no error labels or blacklist rules are inferred.',
               'High frequency and absent RAP IDs alone do not establish an annotation error.',
               'A correct gene ID mapping does not establish correct recognition in the sentence.',
               'Keep entity recognition and support for the specific relation as separate review decisions.',
               'The pooled stratified sample is not an estimate of accuracy across the full database.'])
    return report, pending, frequency_rows, [row for kind in rng for row in samples[kind]], audit_fields


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--association-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, help='New review folder; default: <association-dir>/review')
    parser.add_argument('--sample-per-type', type=int, default=50)
    parser.add_argument('--seed', type=int, default=20261014)
    args = parser.parse_args(argv)
    if args.sample_per_type < 1:
        parser.error('--sample-per-type must be positive')
    output = args.output_dir or args.association_dir / 'review'
    if output.exists():
        raise ValueError('Review directory already exists; protect filled review sheets by selecting a new --output-dir: ' + str(output))
    report, pending, frequency, sample, audit_fields = prepare(args.association_dir, args.sample_per_type, args.seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name('.' + output.name + '.building')
    staging.mkdir(exist_ok=False)
    save_table(staging / 'gene_mapping_review.tsv', audit_fields + ['Sentence_Text', 'Review_Decision', 'Suggested_Gene_Key', 'Notes'], pending)
    frequency_fields = ['Original_Gene_ID', 'Matched_Text', 'Mentions', 'Sentences', 'Articles', 'Mapping_Status',
                        'RAP_IDs', 'Standard_Name_Candidates', 'Example_Sentence_ID', 'Example_Sentence_Text', 'Review_Decision', 'Notes']
    save_table(staging / 'gene_term_frequency.tsv', frequency_fields, frequency)
    sample_fields = ['Relation_Type', 'PMID', 'Sentence_ID', 'Year', 'Gene_Key', 'RAP_ID', 'Gene_Symbol',
                     'Original_Gene_ID', 'Mapping_Status', 'Candidate_Gene_Keys', 'Ontology_ID', 'Trait_Description',
                     'Trait_Name_Candidates', 'Variety_ID', 'Variety_Name', 'Variety_Name_Candidates',
                     'Sentence_Text', 'Gene_Correct', 'Trait_Correct', 'Variety_Correct', 'Relation_Supported', 'Notes']
    save_table(staging / 'association_review_sample.tsv', sample_fields, sample)
    (staging / 'review_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    staging.rename(output)
    print('[CHECK] Published hashes, sentence context, counts and GTA trend pairs passed.', flush=True)
    print('[SUMMARY] ' + json.dumps(report['counts'], ensure_ascii=False), flush=True)
    print('[SAMPLE] ' + json.dumps(report['sampling']['sampled_rows']), flush=True)
    print('[OUTPUT] ' + str(output.resolve()), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(2)
