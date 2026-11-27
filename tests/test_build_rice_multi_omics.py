"""Biological correctness checks for reference extraction, using small known sequences."""
import csv
import gzip
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_dataset.build_rice_multi_omics import build, read_oryzabase, split_aliases

A, B = 'Os01g0100100', 'Os01g0100200'
TA, TB = 'Os01t0100100-01', 'Os01t0100200-01'

class TestReferenceExtraction(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / 'tmp'
        temporary_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='omics-test-', dir=str(temporary_root))
        self.folder = Path(self.temporary.name)
        self.assertIn(temporary_root.resolve(), self.folder.resolve().parents)
        self.addCleanup(self.temporary.cleanup)
        self.oryza = self.folder / 'oryza.tsv'
        with self.oryza.open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t', lineterminator='\n')
            w.writerow(['Trait Gene Id', 'CGSNL Gene Symbol', 'Gene symbol synonym(s)',
                        'CGSNL Gene Name', 'Gene name synonym(s)', 'RAP ID'])
            w.writerow(['1', 'G1', 'shared, AMT1;1', 'alpha', 'a name\nwith embedded newline', A])
            w.writerow(['2', 'G2', 'shared', 'beta', 'a name\twith embedded tab', B])
            w.writerow(['3', 'unmapped', '', 'unmapped', '', ''])
        self.gff = self.write_gzip('genes.gff3.gz',
            '1\tRAP\tgene\t1\t4\t.\t+\t.\tID=gene:' + A + ';gene_id=' + A + '\n' +
            '1\tRAP\tmRNA\t1\t4\t.\t+\t.\tID=transcript:' + TA + ';Parent=gene:' + A + '\n' +
            '1\tRAP\tgene\t7\t11\t.\t-\t.\tID=gene:' + B + ';gene_id=' + B + '\n' +
            '1\tRAP\tmRNA\t7\t11\t.\t-\t.\tID=transcript:' + TB + ';Parent=gene:' + B + '\n' +
            '1\tRAP\tCDS\t7\t11\t.\t-\t0\tParent=transcript:' + TB + ';protein_id=P2\n')
        self.dna = self.write_gzip('dna.fa.gz', '>1 chromosome:IRGSP-1.0\nAACGTTAACCGG\n')
        self.cdna = self.write_gzip('cdna.fa.gz', '>' + TA + ' gene:' + A + '\nATGGCC\n>' + TB + ' gene:' + B + '\nATGCCC\n')
        self.pep = self.write_gzip('pep.fa.gz', '>BAJ001 gene:' + A + ' transcript:' + TA + '\nMA\n>P2 gene:' + B + '\nMP\n')

    def write_gzip(self, name, text):
        path = self.folder / name
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_forward_negative_and_nonidentical_protein_ids(self):
        data, report = build(self.oryza, self.gff, self.dna, self.cdna, self.pep)
        self.assertEqual(data['gene_payload'][A]['genomic_seq'], 'AACG')
        self.assertEqual(data['gene_payload'][B]['genomic_seq'], 'CGGTT')
        self.assertEqual(data['gene_payload'][A]['transcripts'][0]['protein_id'], 'BAJ001')
        self.assertEqual(data['gene_payload'][A]['transcripts'][0]['protein_seq'], 'MA')
        self.assertEqual(data['gene_payload'][B]['transcripts'][0]['protein_seq'], 'MP')
        self.assertEqual(data['search_index']['shared'], [A, B])
        self.assertIn('AMT1;1', data['gene_payload'][A]['all_symbols'])
        self.assertEqual(report['counts']['oryzabase_rows_without_rap'], 1)
        self.assertEqual(report['counts']['output_gene_count'], 2)

    def test_quoted_multiline_and_tab_fields_are_not_lost(self):
        genes, stats = read_oryzabase(self.oryza)
        self.assertEqual(stats['oryzabase_rows'], 3)
        self.assertIn('a name\nwith embedded newline', genes[A]['all_names'])
        self.assertIn('a name\twith embedded tab', genes[B]['all_names'])

    def test_out_of_bounds_coordinates_fail(self):
        with gzip.open(self.gff, 'rt', encoding='utf-8') as f:
            content = f.read().replace('gene\t1\t4', 'gene\t1\t40')
        self.write_gzip(self.gff.name, content)
        with self.assertRaisesRegex(ValueError, 'exceeds chromosome'):
            build(self.oryza, self.gff, self.dna, self.cdna, self.pep)

    def test_missing_protein_links_fail(self):
        self.write_gzip(self.pep.name, '>UNKNOWN gene:UNKNOWN\nMA\n')
        with self.assertRaisesRegex(ValueError, 'No cDNA/protein attachments'):
            build(self.oryza, self.gff, self.dna, self.cdna, self.pep)

    def test_gene_name_separators_preserve_semicolon_and_parentheses(self):
        self.assertEqual(split_aliases('AMT1;1, aux/iaa protein, enzyme (a, b)|G1'),
                         ['AMT1;1', 'aux/iaa protein', 'enzyme (a, b)', 'G1'])

if __name__ == '__main__':
    unittest.main()
