"""Behavior checks for categorized filtering and preservation of valid annotations."""
import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rice_noise', ROOT / 'filtration' / 'remove_noise.py')
noise = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(noise)


class NoiseFilterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ricemind-noise-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rule_dir = self.root / 'rules'
        self.rule_dir.mkdir()
        self.rule('gene', 'OryzaGeneID:2268', 'id_text', '1', name='AMT1;1')
        self.rule('variety', '1962', name='GENE')
        self.rule('go', 'GO:1', name='growth')
        self.oger = self.root / 'oger'
        self.sci = self.root / 'scispacy'
        self.phrase = self.root / 'phrase'
        self.output = self.root / 'out'
        header = ['PMID', 'Sentence_ID', 'Trait_ID', 'Standard_Name',
                  'Start', 'End', 'Matched_Text', 'Sentence_Text']
        for tool, base in (('scispacy', self.sci), ('phrase', self.phrase)):
            for category in ('variety', 'go'):
                folder = ('scispacy_' + category + '_result' if tool == 'scispacy'
                          else 'Rice-' + category.upper() + '-annotation-dir')
                path = base / folder / '2025.tsv'
                path.parent.mkdir(parents=True)
                with path.open('w', encoding='utf-8', newline='') as handle:
                    writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
                    writer.writerow(header)
                    bad = '1962' if category == 'variety' else 'GO:1'
                    good = '88' if category == 'variety' else 'GO:2'
                    for entity_id in (bad, good):
                        writer.writerow(['10', '10_1', entity_id, 'name', '0', '1', '1', '1 AMT1;1'])
        for category in ('co', 'go', 'to', 'rto', 'variety'):
            path = self.oger / 'dataset' / category / 'time' / 'pubtator' / '10_1.txt'
            path.parent.mkdir(parents=True)
            path.write_text('10_1|t|1 AMT1;1 GENE growth\n'
                            '10_1\t0\t1\t1\tgene\tOryzaGeneID:2268\n'
                            '10_1\t2\t8\tAMT1;1\tgene\tOryzaGeneID:2268\n'
                            '10_1\t0\t1\t1\tgene\tOryzaGeneID:other\n'
                            '10_1\t9\t13\tGENE\tvariety\t1962\n'
                            '10_1\t14\t20\tgrowth\tbiological_process\tGO:1\n\n', encoding='utf-8')
            (path.parent / 'empty.txt').write_text('', encoding='utf-8')
            (path.parent.parent / 'notes.txt').write_text('not PubTator', encoding='utf-8')

    def rule(self, category, entity_id, mode='id', text='', enabled='1', name='name'):
        path = self.rule_dir / (category + '_blacklist.tsv')
        exists = path.exists()
        with path.open('a', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, noise.RULE_FIELDS, delimiter='\t', lineterminator='\n')
            if not exists:
                writer.writeheader()
            writer.writerow(dict(enabled=enabled, category=category, entity_id=entity_id,
                                 match_type=mode, matched_text=text, standard_name=name, source='test'))
        return path

    def args(self):
        return noise.build_parser().parse_args([
            '--blacklist-dir', str(self.rule_dir), '--oger-root', str(self.oger),
            '--scispacy-root', str(self.sci), '--phrase-root', str(self.phrase),
            '--output-root', str(self.output)])

    def test_filter_copies_audit_and_keeps_same_id_valid_name(self):
        originals = {p: p.read_bytes() for root in (self.oger, self.sci, self.phrase) for p in root.rglob('*') if p.is_file()}
        self.rule('gene', 'OryzaGeneID:other', enabled='0')
        report = noise.run(self.args())
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['file_counts']['oger'], 10)
        self.assertEqual(report['deleted_rows_by_tool'], {'oger': 15, 'scispacy': 2, 'phrasematcher': 2})
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)
        for path in (self.output / 'oger').rglob('10_1.txt'):
            content = path.read_text(encoding='utf-8')
            self.assertIn('10_1|t|1 AMT1;1 GENE growth\n', content)
            self.assertIn('\tAMT1;1\tgene\tOryzaGeneID:2268', content)
            self.assertIn('\t1\tgene\tOryzaGeneID:other', content)
            self.assertNotIn('\t1\tgene\tOryzaGeneID:2268', content)
            self.assertNotIn('\tGENE\tvariety\t1962', content)
            self.assertNotIn('\tbiological_process\tGO:1', content)
        for path in self.output.rglob('2025.tsv'):
            with path.open(encoding='utf-8', newline='') as handle:
                rows = list(csv.DictReader(handle, delimiter='\t'))
            self.assertEqual(len(rows), 1)
            self.assertIn(rows[0]['Trait_ID'], ('88', 'GO:2'))
            self.assertEqual(rows[0]['Sentence_Text'], '1 AMT1;1')
        self.assertEqual(len(list((self.output / 'oger').rglob('empty.txt'))), 5)
        with (self.output / '_audit' / 'rule_statistics.tsv').open(encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle, delimiter='\t'))
        self.assertEqual(sum(int(r['deleted_annotation_rows']) for r in rows), 19)
        self.assertTrue(all(int(r['deleted_annotation_rows']) == 0 for r in rows if r['enabled'] == '0'))
        for path in self.rule_dir.glob('*.tsv'):
            self.assertEqual(path.read_bytes(), (self.output / '_audit' / 'blacklists' / path.name).read_bytes())
        with self.assertRaisesRegex(ValueError, '输出非空'):
            noise.run(self.args())

    def test_dry_run_and_no_write_on_bad_path(self):
        args = self.args()
        args.dry_run = True
        report = noise.run(args)
        self.assertEqual(report['deleted_rows_by_tool']['oger'], 15)
        self.assertFalse(self.output.exists())
        args.phrase_root = self.root / 'absent'
        with self.assertRaises(FileNotFoundError):
            noise.run(args)
        self.assertFalse(self.output.exists())

    def test_no_in_place_or_nested_output(self):
        args = self.args()
        args.in_place = True
        with self.assertRaisesRegex(ValueError, 'in-place'):
            noise.run(args)
        args.in_place = False
        for output in (self.oger, self.oger / 'new', self.root):
            args.output_root = output
            with self.assertRaisesRegex(ValueError, '输出目录必须'):
                noise.run(args)

    def test_strict_text_match_and_one_rule_counts_once(self):
        self.rule('gene', 'OryzaGeneID:2268')
        rules = noise.RuleSet(sorted(self.rule_dir.glob('*.tsv')), True)
        self.assertTrue(rules.blocked('oger', 'gene', 'OryzaGeneID:2268', '1'))
        exact = next(row for row in rules.rows if row['match_type'] == 'id_text')
        self.assertEqual(rules.hits[(exact['rule_key'], 'oger')], 1)
        self.assertEqual(sum(rules.hits.values()), 1)
        self.assertFalse(rules.blocked('oger', 'variety', 'OryzaGeneID:2268', '1'))
        self.rule('gene', 'caseID', 'id_text', 'SD')
        rules = noise.RuleSet(sorted(self.rule_dir.glob('*.tsv')), True)
        self.assertTrue(rules.blocked('oger', 'gene', 'caseID', 'SD'))
        self.assertFalse(rules.blocked('oger', 'gene', 'caseID', 'sd'))
        self.assertFalse(rules.blocked('oger', 'gene', 'caseID', 'SD9'))

    def test_legacy_explicit_file_and_config_selection(self):
        legacy = self.root / 'noise_blacklist.tsv'
        legacy.write_text('enabled\tcategory\tentity_id\tstandard_name\tsource\n1\tvariety\t1962\tGENE\tlegacy\n', encoding='utf-8')
        args = self.args()
        args.blacklist_dir = None
        args.blacklist_file = legacy
        args.dry_run = True
        report = noise.run(args)
        self.assertEqual(report['deleted_rows_by_tool'], {'oger': 5, 'scispacy': 1, 'phrasematcher': 1})
        args.blacklist_file = None
        with patch.dict(os.environ, {'RICEMIND_NOISE_BLACKLIST_FILE': str(legacy)}):
            self.assertEqual(noise.run(args)['deleted_rows_by_tool']['oger'], 5)
            args.blacklist_dir = self.rule_dir
            self.assertEqual(noise.run(args)['deleted_rows_by_tool']['oger'], 15)

    def test_invalid_rules_rejected_before_output(self):
        path = self.rule_dir / 'gene_blacklist.tsv'
        good = path.read_text(encoding='utf-8')
        for bad in (good.replace('\tgene\t', '\tvariety\t'),
                    good.replace('\tid_text\t1\t', '\tid_text\t\t'),
                    good.replace('\tid_text\t1\t', '\tid\t1\t'),
                    good.replace('\tid_text\t', '\tregex\t'),
                    good + good.splitlines(keepends=True)[1]):
            path.write_text(bad, encoding='utf-8')
            with self.assertRaises(ValueError):
                noise.run(self.args())
            self.assertFalse(self.output.exists())
        path.write_text(good, encoding='utf-8')

    def test_failure_report_and_original_preserved(self):
        source = next(self.oger.rglob('10_1.txt'))
        source.write_text('malformed annotation\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            noise.run(self.args())
        report = json.loads((self.output / '_audit' / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(source.read_text(encoding='utf-8'), 'malformed annotation\n')

    def test_repository_rules_preserve_legacy_variety_and_add_only_confirmed_genes(self):
        root = ROOT / 'dict-dir' / 'filtering'
        rules = noise.RuleSet(sorted((root / 'blacklists').glob('*_blacklist.tsv')), True)
        old = noise.RuleSet([root / 'noise_blacklist.tsv'])
        self.assertEqual(len(rules.paths), 6)
        self.assertEqual({k for k in rules.by_id if k[0] == 'variety'}, set(old.by_id))
        self.assertEqual(len(rules.by_id), 18)
        self.assertEqual(set(rules.by_text), {('gene', 'OryzaGeneID:2268', '1'),
                                            ('gene', 'OryzaGeneID:2270', '2'),
                                            ('gene', 'OryzaGeneID:2269', '3')})
        self.assertFalse(rules.blocked('oger', 'gene', 'OryzaGeneID:2268', 'AMT1;1'))

    def test_cleaned_output_feeds_existing_statistics(self):
        spec = importlib.util.spec_from_file_location(
            'statistics_fixture', ROOT / 'tests' / 'test_annotations_statistics.py')
        fixture_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture_module)
        fixture = fixture_module.AnnotationStatisticsTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for path in fixture.oger.rglob('*.txt'):
            sid = path.stem
            if sid != '2_01':
                with path.open('a', encoding='utf-8') as handle:
                    handle.write('{}\t1\t2\t1\tgene\tOryzaGeneID:2268\n'.format(sid))
        args = self.args()
        args.blacklist_dir = None
        args.blacklist_file = self.rule_dir / 'gene_blacklist.tsv'
        args.oger_root, args.scispacy_root, args.phrase_root = fixture.oger, fixture.sci, fixture.phrase
        report = noise.run(args)
        self.assertEqual(report['deleted_rows_by_tool']['oger'], 10)
        stats_args = fixture.args()
        stats_args.oger_root = self.output / 'oger'
        stats_args.scispacy_root = self.output / 'scispacy'
        stats_args.phrase_root = self.output / 'phrasematcher'
        fixture_module.stats.run(stats_args)
        summary = json.loads((fixture.root / 'out' / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['sentence_counts']['input_sentences'], 3)
        self.assertEqual(summary['sentence_counts']['unannotated_sentences'], 1)
        gene = next(row for row in summary['annotation_counts']
                    if row['tool'] == 'oger' and row['category'] == 'gene')
        self.assertEqual(gene['unique_mentions'], 4)
        self.assertEqual(gene['input_annotation_rows'], 20)


if __name__ == '__main__':
    unittest.main()
