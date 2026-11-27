"""Reference integration checks for multiline cells and ambiguous gene mappings."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_dataset.build_gene_master_universal import collect_master, main

A, B, S = 'Os01g0100100', 'Os01g0100200', 'Supplementary_geneID:1'

class TestGeneMaster(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / 'tmp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='gene-master-test-', dir=str(temp_root))
        self.folder = Path(self.temp.name)
        self.assertIn(temp_root.resolve(), self.folder.resolve().parents)
        self.addCleanup(self.temp.cleanup)
        self.files = {role: str(self.folder / filename) for role, filename in (
            ('omics_json', 'omics.json'), ('oryzabase_txt', 'oryza.tsv'),
            ('planteome_txt', 'mapping.tsv'), ('supp_dict_tsv', 'supp.tsv'))}
        Path(self.files['omics_json']).write_text(json.dumps({'gene_payload': {
            A: {'rap_id': A, 'primary_symbol': 'G1', 'all_symbols': ['G1'],
                'transcripts': [], 'location': {'chromosome': '1', 'start': 1, 'end': 4, 'strand': '+'}}
        }}), encoding='utf-8')
        self.write_table(self.files['oryzabase_txt'], [
            ['Trait Gene Id', 'CGSNL Gene Symbol', 'Gene symbol synonym(s)', 'CGSNL Gene Name',
             'Gene name synonym(s)', 'Explanation', 'Trait Class', 'RAP ID', 'MSU ID', 'Gramene ID'],
            ['1', 'G1', 'AMT1;1, enzyme (a, b)', 'gene\nname', 'name synonym',
             'explanation\twith tab', 'class', A + ', ' + B, 'LOC_Os01g1', 'GR:1'],
            ['2', 'G2', '', 'unmapped name', '', 'no locus', 'class', '', '', ''],
        ])
        self.write_table(self.files['planteome_txt'], [
            ['RAP_ID', 'External_Source', 'Protein_or_Transcript_ID'],
            [A, 'protein_id', 'P1'], [B, 'protein_id', 'P1'], [A, 'EMBL', 'AP0001'],
        ])
        self.write_table(self.files['supp_dict_tsv'], [
            ['source', 'dictionary', S, 'g1', 'G1', 'gene'],
            ['source', 'dictionary', S, 'alias1', 'G1', 'gene'],
        ])

    def write_table(self, path, rows):
        with Path(path).open('w', encoding='utf-8', newline='') as f:
            csv.writer(f, delimiter='\t', lineterminator='\n').writerows(rows)

    def arguments(self):
        values = []
        for option, role in (('--omics-json', 'omics_json'), ('--oryzabase-file', 'oryzabase_txt'),
                             ('--protein-mapping', 'planteome_txt'), ('--supp-dict', 'supp_dict_tsv')):
            values.extend([option, self.files[role]])
        return values + ['--output-dir', str(self.folder / 'out')]

    def test_multiple_rap_ids_are_preserved(self):
        master, index, report = collect_master(self.files)
        self.assertIn(A, master)
        self.assertIn(B, master)
        self.assertEqual(index['id_candidates']['oryzageneid:1'], [A, B])
        self.assertEqual(report['counts']['oryzabase_records_with_multiple_raps'], 1)

    def test_longtail_and_supplementary_are_independent(self):
        master, index, report = collect_master(self.files)
        self.assertIsNone(master['OryzaGeneID:2']['IDs']['RAP_ID'])
        self.assertIsNone(master[S]['IDs']['RAP_ID'])
        self.assertEqual(index['id_candidates'][S.casefold()], [S])
        self.assertEqual(set(index['symbol_candidates']['g1']), {A, B, S})
        self.assertIn('alias1', master[S]['Nomenclature']['All_Symbols'])
        self.assertEqual(report['counts']['total_entries'], 4)

    def test_multiline_cells_and_semicolon_names(self):
        master, _, _ = collect_master(self.files)
        self.assertEqual(master[A]['Nomenclature']['CGSNL_Name'], 'gene\nname')
        self.assertEqual(master[A]['Annotations']['Explanation'], 'explanation\twith tab')
        self.assertIn('AMT1;1', master[A]['Nomenclature']['All_Symbols'])
        self.assertIn('enzyme (a, b)', master[A]['Nomenclature']['All_Symbols'])

    def test_sequence_accession_namespace_and_ambiguous_mapping(self):
        master, index, _ = collect_master(self.files)
        self.assertNotIn('AP0001', master[A]['IDs']['Protein_ID'])
        self.assertIn('AP0001', master[A]['IDs']['External_ID'])
        self.assertEqual(index['id_candidates']['p1'], [A, B])

    def test_missing_required_input_fails(self):
        Path(self.files['supp_dict_tsv']).unlink()
        with self.assertRaises(FileNotFoundError):
            collect_master(self.files)

    def test_check_only_does_not_create_outputs(self):
        self.assertEqual(main(self.arguments() + ['--check-only']), 0)
        self.assertFalse((self.folder / 'out').exists())

    def test_existing_master_is_protected(self):
        output = self.folder / 'out'
        output.mkdir()
        marker = output / 'Unified_Gene_Master.json'
        marker.write_text('preserve me', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            main(self.arguments())
        self.assertEqual(marker.read_text(encoding='utf-8'), 'preserve me')

if __name__ == '__main__':
    unittest.main()
