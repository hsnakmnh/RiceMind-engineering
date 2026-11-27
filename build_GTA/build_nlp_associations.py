#!/usr/bin/env python3
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""Build auditable sentence-level GTA/GVA/TVA co-occurrence candidates.

Python 3.8+ stdlib. Requires the gene master and candidate index. Ambiguous or
unmapped genes retain their original ID and an empty RAP_ID. Reads a selected
statistics batch, retains single-tool genes, applies the active per-category
blacklists as an explicit safeguard, and never modifies input annotations.
"""
import argparse
import copy
import csv
import hashlib
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import ricemind_config as config
RESULTS_DIR = Path(config.RESULTS_DIR)
STANDARD_GENE_DIR = Path(config.STANDARD_GENE_DIR)
NOISE_BLACKLIST_DIR = Path(os.environ.get('RICEMIND_NOISE_BLACKLIST_DIR') or
                          getattr(config, 'NOISE_BLACKLIST_DIR', Path(config.BASE_DIR) / 'dict-dir/filtering/blacklists'))

RAP_RE = re.compile(r'Os\d{2}g\d{7}')
SOURCE_DB, EVIDENCE_CODE = 'RiceMind_NLP', 'NLP_Cooccurrence'
GTA_FIELDS = ['RAP_ID', 'Gene_Symbol', 'Ontology_Type', 'Ontology_ID', 'Trait_Description',
              'Evidence_Code', 'Source_DB', 'PMID', 'Sentence_ID', 'Original_Gene_ID',
              'Gene_Key', 'Mapping_Status', 'Candidate_Gene_Keys', 'Trait_Name_Candidates', 'Year', 'Sentence_Text']
GVA_FIELDS = ['Relation_Type', 'Gene_RAP_ID', 'Gene_Symbol', 'Ontology_Type', 'Ontology_ID',
              'Trait_Description', 'Variety_ID', 'Variety_Name', 'Evidence_Code', 'Source_DB',
              'PMID', 'Sentence_ID', 'Original_Gene_ID', 'Gene_Key', 'Mapping_Status',
              'Candidate_Gene_Keys', 'Trait_Name_Candidates', 'Variety_Name_Candidates', 'Year', 'Sentence_Text']
TREND_FIELDS = ['RAP_ID', 'Gene_Symbol', 'Ontology_Type', 'Ontology_ID', 'Trait_Description',
                'Evidence_Code', 'Source_DB', 'Reference', 'Article_Count', 'First_Mention_Year',
                'Original_Gene_ID', 'Gene_Key', 'Mapping_Status', 'Candidate_Gene_Keys',
                'Trait_Name_Candidates', 'Sentence_Count']
AUDIT_FIELDS = ['PMID', 'Sentence_ID', 'Year', 'Original_Gene_ID', 'Matched_Text', 'Start', 'End',
                'Gene_Key', 'RAP_ID', 'Gene_Symbol', 'Mapping_Status', 'Mapping_Method',
                'Candidate_Gene_Keys', 'Standard_Name_Candidates', 'Tools', 'Review_Flags', 'Blacklist_Rule']


def jlist(items):
    return json.dumps(sorted(set(items)), ensure_ascii=False)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require_file(path):
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        raise FileNotFoundError('Missing or empty input: ' + str(path))


class Resolver:
    def __init__(self, master_file, index_file, allow_symbol_fallback=False):
        require_file(master_file)
        require_file(index_file)
        self.master = json.loads(Path(master_file).read_text(encoding='utf-8'))
        self.index = json.loads(Path(index_file).read_text(encoding='utf-8'))
        self.allow_symbol_fallback = allow_symbol_fallback
        if not isinstance(self.master, dict) or not self.master:
            raise ValueError('Gene master is empty or invalid')
        for group in ('id_candidates', 'symbol_candidates'):
            entries = self.index.get(group)
            if not isinstance(entries, dict) or not entries:
                raise ValueError('Candidate index lacks ' + group)
            for alias, targets in entries.items():
                if alias != alias.casefold() or not isinstance(targets, list) or not targets:
                    raise ValueError('Invalid candidate index entry: ' + alias)
                if len(set(targets)) != len(targets) or any(key not in self.master for key in targets):
                    raise ValueError('Index contains duplicate/missing gene keys: ' + alias)
        self.exact = {}
        for key, info in self.master.items():
            if not isinstance(info, dict) or not isinstance(info.get('IDs'), dict):
                raise ValueError('Invalid master entry: ' + key)
            rap = info['IDs'].get('RAP_ID')
            if rap and (not RAP_RE.fullmatch(rap) or rap != key):
                raise ValueError('Invalid canonical RAP ID: ' + key)
            folded = key.casefold()
            if folded in self.exact:
                raise ValueError('Duplicate master keys after case folding: ' + key)
            self.exact[folded] = key
        report = Path(master_file).with_name('Unified_Gene_Master_build_report.json')
        if report.is_file():
            outputs = json.loads(report.read_text(encoding='utf-8')).get('outputs', {})
            for path in (Path(master_file), Path(index_file)):
                recorded = outputs.get(path.name, {}).get('sha256')
                if recorded and sha256(path) != recorded:
                    raise ValueError('Master/index does not match build report: ' + str(path))

    def resolve(self, entity):
        original, names = entity['id'], entity['standard_names']
        if original.casefold() in self.exact:
            candidates, method = [self.exact[original.casefold()]], 'exact_master_key'
        else:
            candidates = sorted(set(self.index['id_candidates'].get(original.casefold(), [])))
            method = 'id_candidates'
        if not candidates and self.allow_symbol_fallback:
            candidates = sorted({key for name in names for key in
                                 self.index['symbol_candidates'].get(name.casefold(), [])})
            method = 'symbol_candidates'
        result = dict(original_id=original, gene_key=original, rap_id='', gene_symbol='',
                      mapping_status='unmapped_id', mapping_method=method,
                      candidate_gene_keys=candidates)
        if len(candidates) > 1:
            result['mapping_status'] = 'ambiguous_symbol' if method == 'symbol_candidates' else 'ambiguous_id'
        elif len(candidates) == 1:
            key = candidates[0]
            info = self.master[key]
            result.update(gene_key=key, rap_id=info['IDs'].get('RAP_ID') or '',
                          gene_symbol=info.get('Nomenclature', {}).get('Primary_Symbol') or unique_name(names))
            if result['rap_id']:
                result['mapping_status'] = 'resolved_rap_by_symbol' if method == 'symbol_candidates' else 'resolved_rap'
            elif key.startswith('Supplementary_geneID:'):
                result['mapping_status'] = 'supplementary_no_rap'
            else:
                result['mapping_status'] = 'reference_no_rap'
        if not result['gene_symbol']:
            result['gene_symbol'] = unique_name(names)
        return result


class Blacklists:
    def __init__(self, folder):
        folder = Path(folder)
        paths = sorted(folder.glob('*_blacklist.tsv')) if folder.is_dir() else []
        if not paths:
            raise ValueError('No category blacklist files found: ' + str(folder))
        self.snapshots, self.lookup = {}, {}
        for path in paths:
            data = path.read_bytes()
            self.snapshots[path.name] = data
            with path.open(encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader((line for line in f if line.strip() and not line.lstrip().startswith('#')), delimiter='\t')
                if not {'enabled', 'category', 'entity_id'} <= set(reader.fieldnames or []):
                    raise ValueError('Blacklist has missing columns: ' + str(path))
                for number, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError('Malformed blacklist row: ' + str(path))
                    enabled = row['enabled'].strip().casefold()
                    if enabled in ('0', 'false', 'no', 'off'):
                        continue
                    if enabled not in ('1', 'true', 'yes', 'on'):
                        raise ValueError('Invalid enabled value in ' + str(path))
                    category, entity_id = row['category'].strip().casefold(), row['entity_id'].strip()
                    mode = row.get('match_type', 'id').strip()
                    matched = row.get('matched_text', '').strip()
                    if category != path.name[:-len('_blacklist.tsv')] or not entity_id:
                        raise ValueError('Blacklist category/ID does not match filename: ' + str(path))
                    if mode not in ('id', 'id_text') or (mode == 'id_text' and not matched) or (mode == 'id' and matched):
                        raise ValueError('Invalid blacklist match_type: ' + str(path))
                    key = (category, entity_id, matched if mode == 'id_text' else None)
                    if key in self.lookup:
                        raise ValueError('Duplicate active blacklist rule: ' + str(key))
                    self.lookup[key] = '{}:{}'.format(path.name, number)

    def match(self, entity):
        category, entity_id, matched = entity['category'], entity['id'], entity['Matched_Text']
        return self.lookup.get((category, entity_id, matched)) or self.lookup.get((category, entity_id, None)) or ''


def unique_name(names):
    return names[0] if len(names) == 1 else ''


def annotations(record):
    if 'merged_annotations' in record:
        raw = record['merged_annotations']
        if not isinstance(raw, list):
            raise ValueError('merged_annotations must be a list')
    else:
        by_tool = record.get('annotations')
        if not isinstance(by_tool, dict):
            raise ValueError('Input has no merged_annotations / annotations')
        raw = []
        for tool, entries in by_tool.items():
            if not isinstance(entries, list):
                raise ValueError('annotations tool entries must be lists')
            raw.extend(dict(entry, tools=entry.get('tools', [tool])) for entry in entries)
    merged = {}
    for entry in raw:
        cat = entry.get('cat')
        if cat not in ('Gene', 'Phenotype', 'Variety'):
            raise ValueError('Unknown annotation category: ' + str(cat))
        if entry.get('id') is None or not str(entry['id']).strip():
            raise ValueError('Entity has no ID')
        entity_id = str(entry['id']).strip()
        start, end = int(entry['start']), int(entry['end'])
        matched = entry['Matched_Text']
        if not isinstance(matched, str) or not (0 <= start < end <= len(record['text'])) or record['text'][start:end] != matched:
            raise ValueError('Entity offsets/text do not match sentence ' + record['sent_id'])
        category = 'gene' if cat == 'Gene' else 'variety' if cat == 'Variety' else str(entry.get('category') or entity_id.split(':')[0]).casefold()
        if category.startswith('co_'):
            category = 'co'
        names = entry.get('standard_names', [])
        if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
            raise ValueError('standard_names must be a string list')
        names = {n.strip() for n in names if n.strip()}
        norm = entry.get('Normalization', '')
        if not isinstance(norm, str):
            raise ValueError('Normalization must be a string')
        if norm.strip():
            names.add(norm.strip())
        tools = entry.get('tools', [entry.get('tool', 'unknown')])
        if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
            raise ValueError('tools must be a string list')
        key = (cat, entity_id, start, end)
        item = merged.setdefault(key, dict(id=entity_id, cat=cat, category=category, start=start, end=end,
                                          Matched_Text=matched, standard_names=set(), tools=set()))
        item['standard_names'].update(names)
        item['tools'].update(tools)
    for item in merged.values():
        item['standard_names'], item['tools'] = sorted(item['standard_names']), sorted(item['tools'])
    return list(merged.values())


def records(path, years):
    seen = set()
    with Path(path).open(encoding='utf-8-sig') as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError('Expected one sentence object per JSONL line: ' + str(number))
            for field in ('PMID', 'sent_id', 'text', 'year'):
                if field not in record:
                    raise ValueError('Sentence lacks ' + field + ' at line ' + str(number))
            if not isinstance(record['text'], str) or not record['text'] or not str(record['PMID']) or record['PMID'] is None:
                raise ValueError('Invalid PMID/sentence text at line ' + str(number))
            sid = record['sent_id']
            if not isinstance(sid, str) or not sid or sid in seen:
                raise ValueError('Empty or duplicate sentence ID at line ' + str(number))
            seen.add(sid)
            year = int(record['year'])
            if not 1800 <= year <= 2100:
                raise ValueError('Invalid publication year: ' + sid)
            if year not in years:
                raise ValueError('Sentence is outside selected years: ' + sid)
            record.update(PMID=str(record['PMID']), year=year)
            yield record


def grouped_entities(entities, kind):
    groups = {}
    for entity in entities:
        if entity['cat'] != kind:
            continue
        key = entity['resolution']['gene_key'] if kind == 'Gene' else entity['id']
        group = groups.setdefault(key, dict(id=key, names=set(), original_ids=set(), statuses=set(), candidates=set(), symbols=set(), rap_id='', gene_symbol=''))
        group['names'].update(entity['standard_names'])
        if kind == 'Gene':
            r = entity['resolution']
            group['original_ids'].add(entity['id'])
            group['statuses'].add(r['mapping_status'])
            group['candidates'].update(r['candidate_gene_keys'])
            if r['gene_symbol']:
                group['symbols'].add(r['gene_symbol'])
            if group['rap_id'] and r['rap_id'] and group['rap_id'] != r['rap_id']:
                raise ValueError('Inconsistent RAP identity for gene key ' + key)
            group['rap_id'] = group['rap_id'] or r['rap_id']
            group['gene_symbol'] = group['gene_symbol'] or r['gene_symbol']
    return groups


def gene_columns(group):
    return dict(RAP_ID=group['rap_id'], Gene_Symbol=unique_name(sorted(group['symbols'])), Gene_Key=group['id'],
                Original_Gene_ID=';'.join(sorted(group['original_ids'])),
                Mapping_Status='|'.join(sorted(group['statuses'])), Candidate_Gene_Keys=jlist(group['candidates']))


def trait_columns(group):
    names = sorted(group['names'])
    return dict(Ontology_ID=group['id'], Ontology_Type=group['id'].split(':')[0],
                Trait_Description=unique_name(names), Trait_Name_Candidates=jlist(names))


def audit_row(record, entity, rule=''):
    r = entity.get('resolution') or dict(gene_key='', rap_id='', gene_symbol='', mapping_status='blacklisted',
                                        mapping_method='confirmed_blacklist', candidate_gene_keys=[])
    flags = []
    if entity['Matched_Text'].isdecimal():
        flags.append('numeric_gene_surface')
    if len(entity['standard_names']) > 1:
        flags.append('conflicting_standard_names')
    return dict(PMID=record['PMID'], Sentence_ID=record['sent_id'], Year=record['year'],
        Original_Gene_ID=entity['id'], Matched_Text=entity['Matched_Text'], Start=entity['start'], End=entity['end'],
        Gene_Key=r['gene_key'], RAP_ID=r['rap_id'], Gene_Symbol=r['gene_symbol'], Mapping_Status=r['mapping_status'],
        Mapping_Method=r['mapping_method'], Candidate_Gene_Keys=jlist(r['candidate_gene_keys']),
        Standard_Name_Candidates=jlist(entity['standard_names']), Tools=jlist(entity['tools']),
        Review_Flags=jlist(flags), Blacklist_Rule=rule)


def process(input_file, resolver, rules, years, writers=None):
    writers = writers or {}
    counts, mappings, removed, rule_hits, trends = Counter(), Counter(), Counter(), Counter(), {}
    for record in records(input_file, years):
        counts['input_sentences'] += 1
        kept, excluded = [], []
        raw = annotations(record)
        counts['input_unique_mentions'] += len(raw)
        for entity in raw:
            rule = rules.match(entity)
            if entity['cat'] == 'Gene':
                counts['input_gene_mentions'] += 1
            if rule:
                removed[entity['category']] += 1
                rule_hits[rule] += 1
                excluded.append(dict(entity, blacklist_rule=rule))
                if entity['cat'] == 'Gene':
                    mappings['blacklisted'] += 1
                    if 'audit' in writers:
                        writers['audit'].writerow(audit_row(record, entity, rule))
                continue
            if entity['cat'] == 'Gene':
                entity['resolution'] = resolver.resolve(entity)
                mappings[entity['resolution']['mapping_status']] += 1
                if entity['Matched_Text'].isdecimal():
                    counts['retained_numeric_gene_mentions_for_review'] += 1
                if 'audit' in writers:
                    writers['audit'].writerow(audit_row(record, entity))
            kept.append(entity)
        counts['retained_unique_mentions'] += len(kept)
        genes, traits, varieties = (grouped_entities(kept, kind) for kind in ('Gene', 'Phenotype', 'Variety'))
        counts['gene_sentences'] += bool(genes)
        counts['multi_category_sentences'] += sum(bool(x) for x in (genes, traits, varieties)) >= 2
        counts['gene_trait_sentences'] += bool(genes) and bool(traits)
        base = dict(Evidence_Code=EVIDENCE_CODE, Source_DB=SOURCE_DB, PMID=record['PMID'],
                    Sentence_ID=record['sent_id'], Year=record['year'], Sentence_Text=record['text'])
        if 'normalized' in writers:
            output = dict(record, normalized_entities=kept, excluded_annotations=excluded,
                          normalized_has_gene=bool(genes),
                          normalized_categories=[name for name, group in (('Gene', genes), ('Phenotype', traits), ('Variety', varieties)) if group],
                          normalized_is_multi_entity=sum(bool(x) for x in (genes, traits, varieties)) >= 2)
            writers['normalized'].write(json.dumps(output, ensure_ascii=False) + '\n')
        for gene, trait in itertools.product(genes.values(), traits.values()):
            row = dict(base, **gene_columns(gene), **trait_columns(trait))
            counts['gta_rows'] += 1
            counts['gta_rows_with_rap'] += bool(gene['rap_id'])
            if 'gta' in writers:
                writers['gta'].writerow(row)
            key = (gene['id'], trait['id'])
            if key not in trends:
                trends[key] = dict(gene=copy.deepcopy(gene), trait=copy.deepcopy(trait), pmids=set(), sids=set(), years=set())
            trend = trends[key]
            trend['gene']['original_ids'].update(gene['original_ids'])
            trend['gene']['statuses'].update(gene['statuses'])
            trend['gene']['candidates'].update(gene['candidates'])
            trend['gene']['symbols'].update(gene['symbols'])
            trend['trait']['names'].update(trait['names'])
            trend['pmids'].add(record['PMID'])
            trend['sids'].add(record['sent_id'])
            trend['years'].add(record['year'])
        for gene, variety in itertools.product(genes.values(), varieties.values()):
            g = gene_columns(gene)
            row = dict(base, **{k: v for k, v in g.items() if k != 'RAP_ID'}, Gene_RAP_ID=g['RAP_ID'],
                Relation_Type='GVA', Variety_ID=variety['id'], Variety_Name=unique_name(sorted(variety['names'])),
                Variety_Name_Candidates=jlist(variety['names']))
            counts['gva_rows'] += 1
            if 'gva' in writers:
                writers['gva'].writerow(row)
        for trait, variety in itertools.product(traits.values(), varieties.values()):
            row = dict(base, **trait_columns(trait), Relation_Type='TVA', Variety_ID=variety['id'],
                       Variety_Name=unique_name(sorted(variety['names'])), Variety_Name_Candidates=jlist(variety['names']))
            counts['tva_rows'] += 1
            if 'gva' in writers:
                writers['gva'].writerow(row)
        if counts['input_sentences'] % 10000 == 0:
            print('[PROGRESS] Sentences: {:,}'.format(counts['input_sentences']), flush=True)
    if not counts['input_sentences']:
        raise ValueError('Input corpus contains no sentence records')
    for key in ('input_gene_mentions', 'gene_sentences', 'multi_category_sentences', 'gene_trait_sentences',
                'gta_rows', 'gva_rows', 'tva_rows', 'gta_rows_with_rap', 'retained_numeric_gene_mentions_for_review'):
        counts.setdefault(key, 0)
    counts['unique_gta_pairs'] = len(trends)
    if 'trend' in writers:
        for key, item in sorted(trends.items()):
            row = dict(gene_columns(item['gene']), **trait_columns(item['trait']), Evidence_Code=EVIDENCE_CODE,
                       Source_DB=SOURCE_DB, Reference=';'.join(sorted(item['pmids'])), Article_Count=len(item['pmids']),
                       First_Mention_Year=min(item['years']), Sentence_Count=len(item['sids']))
            writers['trend'].writerow(row)
    return dict(counts=dict(counts), gene_mapping_mentions=dict(mappings),
                excluded_mentions_by_category=dict(removed), blacklist_rule_hits=dict(rule_hits))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--stats-dir', type=Path, help='Selected completed statistics directory')
    selection.add_argument('--input-file', type=Path, help='Explicit sentence annotation JSONL')
    p.add_argument('--master-file', type=Path, default=STANDARD_GENE_DIR / 'Unified_Gene_Master.json')
    p.add_argument('--index-file', type=Path, default=STANDARD_GENE_DIR / 'Unified_Gene_Alias_Index.json')
    p.add_argument('--blacklist-dir', type=Path, default=NOISE_BLACKLIST_DIR)
    p.add_argument('--start-year', type=int, default=2025)
    p.add_argument('--end-year', type=int, default=2026)
    p.add_argument('--allow-symbol-fallback', action='store_true', help='Explicitly enable recorded fallback to symbol candidates')
    p.add_argument('--check-only', action='store_true', help='Validate and count without writing output')
    p.add_argument('--output-dir', type=Path, help='New result directory; existing directories are rejected')
    args = p.parse_args(argv)
    if args.start_year > args.end_year:
        p.error('--start-year must not exceed --end-year')
    input_file = args.input_file or args.stats_dir / 'all_sentences_annotations.jsonl'
    for path in (input_file, args.master_file, args.index_file):
        require_file(path)
    resolver, rules = Resolver(args.master_file, args.index_file, args.allow_symbol_fallback), Blacklists(args.blacklist_dir)
    inputs = {label: dict(path=str(path.resolve()), sha256=sha256(path)) for label, path in (
        ('sentences', input_file), ('master', args.master_file), ('candidate_index', args.index_file))}
    print('[INPUT] Sentences: ' + str(input_file), flush=True)
    print('[INPUT] Gene master: ' + str(args.master_file), flush=True)
    print('[INPUT] Candidate index: ' + str(args.index_file), flush=True)
    print('[INPUT] Active blacklist rules: ' + str(len(rules.lookup)), flush=True)
    years = set(range(args.start_year, args.end_year + 1))
    output = args.output_dir or RESULTS_DIR / 'associations/keyword_filtered' / (
        datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + str(os.getpid()))
    if args.check_only:
        summary = process(input_file, resolver, rules, years)
        print('[SUMMARY] ' + json.dumps(summary, ensure_ascii=False), flush=True)
        print('[CHECK] Passed; no output files written.', flush=True)
        return 0
    if output.exists():
        raise ValueError('Output directory already exists; choose a new --output-dir: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name('.' + output.name + '.building-' + str(os.getpid()))
    staging.mkdir(exist_ok=False)
    try:
        with ExitStack() as stack:
            writers = {}
            for key, filename, fields in (
                ('gta', 'NLP_Rice_GTA_Database.tsv', GTA_FIELDS),
                ('gva', 'NLP_Rice_GVA_TVA_Database.tsv', GVA_FIELDS),
                ('trend', 'NLP_Rice_GTA_Trend.tsv', TREND_FIELDS),
                ('audit', 'gene_normalization_audit.tsv', AUDIT_FIELDS)):
                handle = stack.enter_context((staging / filename).open('w', encoding='utf-8', newline=''))
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t', lineterminator='\n')
                writer.writeheader()
                writers[key] = writer
            writers['normalized'] = stack.enter_context((staging / 'normalized_sentences.jsonl').open('w', encoding='utf-8', newline='\n'))
            summary = process(input_file, resolver, rules, years, writers)
        for label, record in inputs.items():
            if sha256(record['path']) != record['sha256']:
                raise ValueError('Input changed while processing: ' + label)
        snapshot = staging / '_audit/blacklists'
        snapshot.mkdir(parents=True)
        for name, data in rules.snapshots.items():
            (snapshot / name).write_bytes(data)
        summary.update(status='complete', created_at=datetime.now().astimezone().isoformat(),
            years=sorted(years), inputs=inputs, allow_symbol_fallback=args.allow_symbol_fallback,
            blacklist_files=[dict(filename=name, sha256=hashlib.sha256(data).hexdigest()) for name, data in rules.snapshots.items()],
            outputs={path.name: dict(size_bytes=path.stat().st_size, sha256=sha256(path)) for path in staging.iterdir() if path.is_file()},
            notes=['All relations are sentence co-occurrence candidates; causal or regulatory relations are not inferred.',
                   'Ambiguous/unmapped genes retain original IDs, blank RAP_ID and candidate lists.',
                   'Confirmed blacklists are reapplied to merged mentions and recorded; existing input/statistics files are unchanged.',
                   'First_Mention_Year is the earliest year in this selected input scope.',
                   'Input sentences are retained even when they have no remaining annotations; strict reliability flags are not filters.'])
        (staging / 'association_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staging.rename(output)
    except Exception as error:
        (staging / 'FAILED.json').write_text(json.dumps(dict(status='failed', error=str(error)), ensure_ascii=False) + '\n', encoding='utf-8')
        raise
    print('[SUMMARY] Sentences={:,}; GTA={:,}; GVA={:,}; TVA={:,}; unique GTA pairs={:,}'.format(
        summary['counts']['input_sentences'], summary['counts']['gta_rows'], summary['counts']['gva_rows'],
        summary['counts']['tva_rows'], summary['counts']['unique_gta_pairs']), flush=True)
    print('[OUTPUT] ' + str(output.resolve()), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(2)
