"""Integration tests for candidate identity, relation deduplication and provenance."""
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_GTA import build_nlp_associations as assoc

A, B, L, S = 'Os01g0100100', 'Os01g0100200', 'OryzaGeneID:2', 'Supplementary_geneID:1'


def entity(text, matched, entity_id, cat='Gene', occurrence=0, names=None, tools=None):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(matched, start + 1)
    return dict(id=entity_id, cat=cat, start=start, end=start + len(matched), Matched_Text=matched,
                standard_names=names if names is not None else [matched], tools=tools or ['oger'])


def sentence(sid, pmid, year, text, entities):
    return dict(sent_id=sid, PMID=pmid, year=year, text=text,
                merged_annotations=entities, is_strict_reliable=False)


class TestAssociations(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / 'tmp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='association-test-', dir=str(temp_root))
        self.root = Path(self.temp.name)
        self.assertIn(temp_root.resolve(), self.root.resolve().parents)
        self.addCleanup(self.temp.cleanup)
        self.master = self.root / 'master.json'
        self.index = self.root / 'index.json'
        self.corpus = self.root / 'sentences.jsonl'
        self.blacklists = self.root / 'blacklists'
        self.blacklists.mkdir()
        entries = {key: dict(IDs={'RAP_ID': key if key in (A, B) else None},
                    Nomenclature={'Primary_Symbol': name, 'All_Symbols': [name]})
                   for key, name in ((A, 'G1'), (B, 'G2'), (L, 'L1'), (S, 'S1'))}
        self.master.write_text(json.dumps(entries), encoding='utf-8')
        ids = {key.casefold(): [key] for key in entries}
        ids.update({'oryzageneid:1': [A], 'oryzageneid:10': [A],
                    'oryzageneid:9': [A, B], 'oryzageneid:2268': [A]})
        self.index.write_text(json.dumps(dict(id_candidates=ids,
            symbol_candidates={'g1': [A], 'g2': [B], 'shared': [A, B]})), encoding='utf-8')
        header = ['enabled', 'category', 'entity_id', 'match_type', 'matched_text', 'standard_name', 'source']
        with (self.blacklists / 'gene_blacklist.tsv').open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t')
            w.writerow(header)
            w.writerow([1, 'gene', 'OryzaGeneID:2268', 'id_text', '1', 'AMT1;1', 'confirmed test rule'])
        with (self.blacklists / 'variety_blacklist.tsv').open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t')
            w.writerow(header)
            w.writerow([1, 'variety', 'BAD', 'id', '', 'common word', 'confirmed test rule'])

    def resolver(self, fallback=False):
        return assoc.Resolver(self.master, self.index, fallback)

    def write_corpus(self, records):
        self.corpus.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')

    def process(self, records):
        self.write_corpus(records)
        buffers, writers = {}, {}
        for key, fields in (('gta', assoc.GTA_FIELDS), ('gva', assoc.GVA_FIELDS),
                            ('trend', assoc.TREND_FIELDS), ('audit', assoc.AUDIT_FIELDS)):
            buffers[key] = io.StringIO()
            w = csv.DictWriter(buffers[key], fields, delimiter='\t', lineterminator='\n')
            w.writeheader()
            writers[key] = w
        buffers['normalized'] = io.StringIO()
        writers['normalized'] = buffers['normalized']
        report = assoc.process(self.corpus, self.resolver(), assoc.Blacklists(self.blacklists), {2025, 2026}, writers)
        tables = {key: list(csv.DictReader(io.StringIO(buf.getvalue()), delimiter='\t'))
                  for key, buf in buffers.items() if key != 'normalized'}
        normalized = [json.loads(line) for line in buffers['normalized'].getvalue().splitlines()]
        return report, tables, normalized

    def test_ambiguous_id_is_not_resolved_by_a_convenient_symbol(self):
        r = self.resolver(True).resolve({'id': 'OryzaGeneID:9', 'standard_names': ['G1']})
        self.assertEqual(r['mapping_status'], 'ambiguous_id')
        self.assertEqual(r['gene_key'], 'OryzaGeneID:9')
        self.assertEqual(r['rap_id'], '')
        self.assertEqual(r['candidate_gene_keys'], [A, B])

    def test_unique_longtail_supplementary_and_unknown(self):
        resolver = self.resolver()
        for entity_id, status, rap in (('OryzaGeneID:1', 'resolved_rap', A),
                                       (L, 'reference_no_rap', ''), (S, 'supplementary_no_rap', ''),
                                       ('OryzaGeneID:404', 'unmapped_id', '')):
            value = resolver.resolve({'id': entity_id, 'standard_names': ['G1']})
            self.assertEqual((value['mapping_status'], value['rap_id']), (status, rap))
        self.assertEqual(resolver.resolve({'id': 'OryzaGeneID:404', 'standard_names': ['G1']})['gene_key'], 'OryzaGeneID:404')

    def test_same_canonical_gene_is_one_pair_and_single_tool_genes_are_kept(self):
        text = 'G1 and G1 affect growth in IR64.'
        first = entity(text, 'G1', 'OryzaGeneID:1')
        duplicate = dict(first, tools=['another-tool'])
        second = entity(text, 'G1', 'OryzaGeneID:10', occurrence=1)
        report, tables, _ = self.process([sentence('1_01', '1', 2025, text, [first, duplicate, second,
            entity(text, 'growth', 'GO:1', 'Phenotype'), entity(text, 'IR64', '55', 'Variety')])])
        self.assertEqual(report['counts']['input_unique_mentions'], 4)
        self.assertEqual((report['counts']['gta_rows'], report['counts']['gva_rows'], report['counts']['tva_rows']), (1, 1, 1))
        self.assertEqual(tables['gta'][0]['RAP_ID'], A)
        self.assertEqual(tables['gta'][0]['Original_Gene_ID'], 'OryzaGeneID:1;OryzaGeneID:10')

    def test_numeric_rule_preserves_full_name_of_same_gene(self):
        text = '1 and AMT1;1 affect growth.'
        report, tables, normalized = self.process([sentence('1_01', '1', 2025, text, [
            entity(text, '1', 'OryzaGeneID:2268'), entity(text, 'AMT1;1', 'OryzaGeneID:2268'),
            entity(text, 'growth', 'GO:1', 'Phenotype')])])
        self.assertEqual(report['excluded_mentions_by_category']['gene'], 1)
        self.assertEqual(report['gene_mapping_mentions']['blacklisted'], 1)
        self.assertEqual(report['counts']['gta_rows'], 1)
        self.assertEqual(len(normalized[0]['excluded_annotations']), 1)
        self.assertEqual({r['Mapping_Status'] for r in tables['audit']}, {'blacklisted', 'resolved_rap'})

    def test_article_count_and_earliest_input_year(self):
        text = 'G1 affects growth.'
        records = [sentence(sid, pmid, year, text, [entity(text, 'G1', 'OryzaGeneID:1'),
                   entity(text, 'growth', 'GO:1', 'Phenotype')])
                   for sid, pmid, year in (('1_01', '1', 2025), ('1_02', '1', 2025), ('2_01', '2', 2026))]
        report, tables, _ = self.process(records)
        self.assertEqual(report['counts']['unique_gta_pairs'], 1)
        trend = tables['trend'][0]
        self.assertEqual((trend['Article_Count'], trend['Sentence_Count'], trend['First_Mention_Year']), ('2', '3', '2025'))

    def test_pair_provenance_does_not_leak_between_traits(self):
        one, two = 'G1 affects growth and height.', 'G1 affects growth.'
        _, tables, _ = self.process([
            sentence('1_01', '1', 2025, one, [entity(one, 'G1', 'OryzaGeneID:1'),
                entity(one, 'growth', 'GO:1', 'Phenotype'), entity(one, 'height', 'TO:2', 'Phenotype')]),
            sentence('2_01', '2', 2026, two, [entity(two, 'G1', 'OryzaGeneID:10'), entity(two, 'growth', 'GO:1', 'Phenotype')])])
        height = next(r for r in tables['trend'] if r['Ontology_ID'] == 'TO:2')
        self.assertEqual(height['Original_Gene_ID'], 'OryzaGeneID:1')
        self.assertEqual(height['Article_Count'], '1')

    def test_no_annotation_sentences_and_ambiguous_genes_are_retained(self):
        text = 'G1 affects growth.'
        report, tables, normalized = self.process([
            sentence('1_01', '1', 2025, text, [entity(text, 'G1', 'OryzaGeneID:9'), entity(text, 'growth', 'GO:1', 'Phenotype')]),
            sentence('2_01', '2', 2026, 'Rice grows.', [])])
        self.assertEqual(report['counts']['input_sentences'], 2)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(tables['gta'][0]['RAP_ID'], '')
        self.assertEqual(json.loads(tables['gta'][0]['Candidate_Gene_Keys']), [A, B])
        self.assertFalse(normalized[1]['normalized_has_gene'])

    def test_incorrect_offsets_and_duplicate_sentence_ids_fail(self):
        text = 'G1 affects growth.'
        bad = entity(text, 'G1', 'OryzaGeneID:1')
        bad['end'] = 3
        with self.assertRaisesRegex(ValueError, 'offsets'):
            self.process([sentence('1_01', '1', 2025, text, [bad])])
        empty = sentence('1_01', '1', 2025, text, [])
        with self.assertRaisesRegex(ValueError, 'duplicate sentence'):
            self.process([empty, empty])

    def test_conflicting_unmapped_names_are_not_arbitrarily_selected(self):
        text = 'X1 and X2 affect growth.'
        _, tables, _ = self.process([sentence('1_01', '1', 2025, text, [
            entity(text, 'X1', 'UNKNOWN:1'), entity(text, 'X2', 'UNKNOWN:1'),
            entity(text, 'growth', 'GO:1', 'Phenotype')])])
        self.assertEqual(tables['gta'][0]['Gene_Symbol'], '')
        self.assertEqual(tables['gta'][0]['RAP_ID'], '')

    def test_actual_statistics_record_schema_is_accepted(self):
        from filtration.annotations_statistics import Collector, make_sentence_record
        text, sid = 'G1 affects growth.', '1_01'
        corpus = {sid: dict(PMID='1', year=2025, text=text)}
        collector = Collector(corpus, {sid}, {('gene', 'OryzaGeneID:1'): {'G1'}})
        collector.add('oger', sid, 0, 2, 'G1', 'gene', 'OryzaGeneID:1')
        collector.add('scispacy', sid, 11, 17, 'growth', 'go', 'GO:1', 'growth')
        collector.add('phrasematcher', sid, 11, 17, 'growth', 'go', 'GO:1', 'growth')
        row = make_sentence_record(sid, corpus[sid], collector.annotations[sid])
        self.assertFalse(row['is_strict_reliable'])
        report, tables, _ = self.process([row])
        self.assertEqual(report['counts']['gta_rows'], 1)
        self.assertEqual(tables['gta'][0]['RAP_ID'], A)
    def args(self):
        return ['--input-file', str(self.corpus), '--master-file', str(self.master), '--index-file', str(self.index),
                '--blacklist-dir', str(self.blacklists), '--output-dir', str(self.root / 'out')]

    def test_check_only_and_formal_output(self):
        text = 'G1 affects growth.'
        self.write_corpus([sentence('1_01', '1', 2025, text, [entity(text, 'G1', 'OryzaGeneID:1'), entity(text, 'growth', 'GO:1', 'Phenotype')])])
        self.assertEqual(assoc.main(self.args() + ['--check-only']), 0)
        self.assertFalse((self.root / 'out').exists())
        self.assertEqual(assoc.main(self.args()), 0)
        output = self.root / 'out'
        summary = json.loads((output / 'association_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['counts']['gta_rows'], 1)
        self.assertTrue((output / '_audit/blacklists/gene_blacklist.tsv').is_file())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            assoc.main(self.args())

    def test_missing_index_and_empty_master_fail(self):
        self.master.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.resolver()
        self.index.unlink()
        with self.assertRaises(FileNotFoundError):
            self.resolver()

    def test_symbol_fallback_is_opt_in(self):
        e = {'id': 'NEW:missing', 'standard_names': ['G1']}
        self.assertEqual(self.resolver().resolve(e)['rap_id'], '')
        self.assertEqual(self.resolver(True).resolve(e)['rap_id'], A)

if __name__ == '__main__':
    unittest.main()
