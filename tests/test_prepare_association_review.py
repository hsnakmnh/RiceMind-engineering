"""Review material integration checks using the association builder's real output."""
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_GTA import build_nlp_associations as assoc
from build_GTA import prepare_association_review as review

A, B = 'Os01g0100100', 'Os01g0100200'


class TestAssociationReview(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / 'tmp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='review-test-', dir=str(temp_root))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        master = self.root / 'master.json'
        index = self.root / 'index.json'
        master.write_text(json.dumps({key: dict(IDs={'RAP_ID': key},
            Nomenclature={'Primary_Symbol': name}) for key, name in ((A, 'G1'), (B, 'G2'))}), encoding='utf-8')
        index.write_text(json.dumps(dict(
            id_candidates={'oryzageneid:1': [A], 'oryzageneid:9': [A, B], 'oryzageneid:2268': [A]},
            symbol_candidates={'g1': [A], 'g2': [B]})), encoding='utf-8')
        blacklist = self.root / 'blacklists'
        blacklist.mkdir()
        (blacklist / 'gene_blacklist.tsv').write_text(
            'enabled\tcategory\tentity_id\tmatch_type\tmatched_text\n'
            '1\tgene\tOryzaGeneID:2268\tid_text\t1\n', encoding='utf-8')

        def entity(text, matched, identifier, cat):
            start = text.index(matched)
            return dict(id=identifier, cat=cat, start=start, end=start + len(matched),
                        Matched_Text=matched, standard_names=[matched], tools=['oger'])

        corpus = self.root / 'sentences.jsonl'
        records = []
        for sid, text, gene_names in (
                ('1_0001', 'G1 and Amb act in rice growth in IR64 with 1.\nA second clause.',
                 [('G1', 'OryzaGeneID:1'), ('Amb', 'OryzaGeneID:9'), ('1.', 'OryzaGeneID:2268')]),
                ('2_0001', 'Unknown supports rice growth in IR64.', [('Unknown', 'OryzaGeneID:404')])):
            entities = []
            for name, identifier in gene_names:
                # Use the final numeric 1 rather than the 1 inside G1.
                if name == '1.':
                    entry = entity(text, name, identifier, 'Gene')
                    entry.update(Matched_Text='1', end=entry['start'] + 1)
                    entities.append(entry)
                else:
                    entities.append(entity(text, name, identifier, 'Gene'))
            entities.extend([entity(text, 'growth', 'TO:1', 'Phenotype'),
                             entity(text, 'IR64', 'V:1', 'Variety')])
            records.append(dict(PMID=sid.split('_')[0], sent_id=sid, text=text, year=2025,
                                merged_annotations=entities))
        corpus.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        self.batch = self.root / 'batch'
        with redirect_stdout(io.StringIO()):
            assoc.main(['--input-file', str(corpus), '--master-file', str(master), '--index-file', str(index),
                        '--blacklist-dir', str(blacklist), '--output-dir', str(self.batch)])

    def test_reports_preserve_context_pending_counts_and_blank_decisions(self):
        report, pending, frequency, sample, fields = review.prepare(self.batch)
        self.assertEqual(report['counts']['gene_mapping_review_mentions'], 2)
        self.assertEqual(report['counts']['gene_mapping_review_ids'], 2)
        self.assertEqual(report['counts']['retained_gene_mentions'], 3)
        self.assertEqual(report['counts']['gta_rap_genes'], 1)
        self.assertEqual(report['counts']['unique_rap_gta_pairs'], 1)
        self.assertEqual({row['Original_Gene_ID'] for row in pending}, {'OryzaGeneID:9', 'OryzaGeneID:404'})
        self.assertTrue(all(row['Review_Decision'] == '' and row['Notes'] == '' for row in pending))
        self.assertTrue(any('\n' in row['Sentence_Text'] for row in pending))
        self.assertEqual(sum(row['Mentions'] for row in frequency), 3)
        self.assertNotIn('1', {row['Matched_Text'] for row in frequency})
        self.assertEqual(len(sample), 8)

    def test_sample_is_reproducible_and_limits_each_relation_type(self):
        first = review.prepare(self.batch, 1, 7)[3]
        second = review.prepare(self.batch, 1, 7)[3]
        self.assertEqual(first, second)
        self.assertEqual([row['Relation_Type'] for row in first], ['GTA', 'GVA', 'TVA'])

    def test_changed_published_input_is_rejected(self):
        with (self.batch / 'gene_normalization_audit.tsv').open('a', encoding='utf-8') as handle:
            handle.write('\n')
        with self.assertRaisesRegex(ValueError, 'changed published'):
            review.prepare(self.batch)

    def test_inconsistent_summary_is_rejected(self):
        path = self.batch / 'association_summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['counts']['gta_rows'] += 1
        path.write_text(json.dumps(summary), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'gta_rows'):
            review.prepare(self.batch)

    def test_write_round_trip_and_protect_filled_sheet(self):
        with redirect_stdout(io.StringIO()):
            review.main(['--association-dir', str(self.batch), '--sample-per-type', '1'])
        out = self.batch / 'review'
        with (out / 'association_review_sample.tsv').open(encoding='utf-8', newline='') as handle:
            self.assertEqual(len(list(csv.DictReader(handle, delimiter='\t'))), 3)
        sheet = out / 'gene_mapping_review.tsv'
        old = sheet.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            review.main(['--association-dir', str(self.batch)])
        self.assertEqual(sheet.read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
