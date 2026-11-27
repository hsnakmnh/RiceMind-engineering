import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_sentence_data import json_records, prepare, sha256, validate_filtered
from tools.check_resources import check_entries
from filtration.annotations_statistics import DICT_NAMES, load_standard_names


class CorpusPackagingTests(unittest.TestCase):
    def test_streaming_unicode_escape_and_tiny_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            rows = [{"id": "123_0001", "text": 'Rice "quoted" 水稻 \\ text'},
                    {"id": "456_0001", "text": "Second sentence"}]
            path.write_text(json.dumps(rows, ensure_ascii=True), encoding="utf-8")
            self.assertEqual(list(json_records(path, chunk_size=3)), rows)

    def test_streaming_rejects_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            for payload in ('[{"id": "x"}', '[{},]', '[{}] false', '{}', '[2]'):
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    list(json_records(path, chunk_size=2))

    def make_corpus(self, folder):
        folder.mkdir()
        (folder / "combined.tsv").write_text(
            "123\t123_0001\tRice A.\n456\t456_0001\tRice B.\n", encoding="utf-8")
        (folder / "year_map.tsv").write_text(
            "Sentence_ID\tYear\n123_0001\t2025\n456_0001\t2026\n", encoding="utf-8")
        return folder

    def test_prepare_keeps_ids_text_and_years_without_refiltering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_corpus(root / "source")
            output = root / "output"
            args = argparse.Namespace(filtered_dir=source, sentence_dir=None, pubtator_dir=None,
                oger_json_dir=None, output_dir=output, start_year=2025, end_year=2026, check_only=False)
            report = prepare(args)
            self.assertFalse(report["filter_applied"])
            self.assertEqual(report["by_year"], {"2025": 1, "2026": 1})
            self.assertEqual(list(json_records(output / "oger.json")),
                [{"id":"123_0001","text":"Rice A."},{"id":"456_0001","text":"Rice B."}])
            self.assertEqual((source/"combined.tsv").read_bytes(), (output/"combined.tsv").read_bytes())
            with self.assertRaises(ValueError):
                prepare(args)

    def test_missing_or_duplicate_year_map_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_corpus(Path(tmp) / "source")
            (source/"year_map.tsv").write_text("Sentence_ID\tYear\n123_0001\t2025\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_filtered(source,[2025,2026])

    def test_manifest_hash_catches_text_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_corpus(Path(tmp)/"source")
            (source/"corpus_manifest.json").write_text(json.dumps({"files":{"combined.tsv":
                {"sha256":sha256(source/"combined.tsv")}}}), encoding="utf-8")
            with (source/"combined.tsv").open("a",encoding="utf-8") as f:
                f.write("\n")
            with self.assertRaises(ValueError):
                validate_filtered(source,[2025,2026])

    def test_resource_manifest_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                check_entries(Path(tmp),[{"path":"../private.txt","bytes":0,"sha256":""}])

    def test_json_input_restores_annual_text_before_author_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            for year, pmid in ((2025, "123"), (2026, "456")):
                (source / (str(year) + "_filtered_sent.json")).write_text(json.dumps([
                    {"id": pmid + "_0001", "text": "Rice gene OsABC1 regulates plant growth and development."},
                    {"id": pmid + "_0002", "text": "This unrelated optical camera measures a light source."}
                ]), encoding="utf-8")
            args = argparse.Namespace(filtered_dir=None, sentence_dir=None, pubtator_dir=None,
                oger_json_dir=source, output_dir=root/"output", start_year=2025, end_year=2026, check_only=False)
            report = prepare(args)
            self.assertEqual(report["reconstructed_by_year"], {"2025": 2, "2026": 2})
            self.assertEqual(report["sentences"], 2)
            stats=json.loads((args.output_dir/"filter_stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["input_sentences"],4)
            self.assertNotIn(".building-",json.dumps(stats))

    def test_pubtator_pipeline_excludes_title_and_emits_consistent_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"source"
            source.mkdir()
            for year, pmid in ((2025,"123"),(2026,"456")):
                (source/("Rice."+str(year)+".pmid-pmcid.txt")).write_text(
                    pmid+"|t|Rice gene OsTITLE1 regulates plant growth.\n"+
                    pmid+"|a|Rice gene OsABC1 regulates plant growth and development.\n\n", encoding="utf-8")
            args=argparse.Namespace(filtered_dir=None,sentence_dir=None,pubtator_dir=source,
                oger_json_dir=None,output_dir=root/"output",start_year=2025,end_year=2026,check_only=False)
            report=prepare(args)
            rows=validate_filtered(args.output_dir,[2025,2026])
            self.assertEqual(report["sentences"],2)
            self.assertTrue(all("OsTITLE1" not in r[2] for r in rows))

    def test_statistics_supports_flat_and_classified_dictionaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            flat=root/"flat"
            flat.mkdir()
            arranged=root/"arranged"
            for name in DICT_NAMES:
                if name.endswith("_gene"):
                    identifier, kind = "OryzaGeneID:" + name, "gene"
                else:
                    identifier, kind = {"co":"CO_320:1","go":"GO:1","to":"TO:1",
                                       "rto":"RTO:1","variety":"1"}[name], name
                row="\t".join(["src","db",identifier,"alias","standard",kind])+"\n"
                (flat/(name+"_oger_dict.tsv")).write_text(row,encoding="utf-8")
                folder=arranged/("genes" if name.endswith("_gene") else "ontology")
                folder.mkdir(parents=True,exist_ok=True)
                (folder/(name+"_oger_dict.tsv")).write_text(row,encoding="utf-8")
            self.assertEqual(load_standard_names(flat),load_standard_names(arranged))


if __name__ == "__main__":
    unittest.main()

