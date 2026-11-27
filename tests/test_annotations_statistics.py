"""Focused integration checks for annotation counts and corpus integrity."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rice_statistics", ROOT / "filtration" / "annotations_statistics.py")
stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stats)


class AnnotationStatisticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ricemind-statistics-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sentences = self.root / "sentences.tsv"
        self.year_map = self.root / "years.tsv"
        self.corpus = {
            "1_01": ("1", "G1 affects growth.", 2025),
            "2_01": ("2", "Rice thrives.", 2025),
            "3_01": ("3", "G1 affects growth.", 2026),
        }
        self.sentences.write_text("".join(
            "{}\t{}\t{}\n".format(pmid, sid, text)
            for sid, (pmid, text, year) in self.corpus.items()), encoding="utf-8")
        self.year_map.write_text("Sentence_ID\tYear\n" + "".join(
            "{}\t{}\n".format(sid, year)
            for sid, (pmid, text, year) in self.corpus.items()), encoding="utf-8")
        self.dicts = self.root / "dicts"
        self.dicts.mkdir()
        for name in stats.DICT_NAMES:
            content = ""
            if name == "oryzabase_gene":
                content = "DB\tgene\tOryzaGeneID:1\tG1\tGene One\tgene\n"
            elif name == "supplementary_gene":
                content = "DB\tgene\tSupplementary_geneID:2\tG\tG\tgene\n"
            elif name == "go":
                content = "DB\tGO\tGO:1\tgrowth\tgrowth\tbiological_process\n"
            (self.dicts / (name + "_oger_dict.tsv")).write_text(content, encoding="utf-8")
        self.oger = self.root / "oger"
        self.sci = self.root / "scispacy"
        self.phrase = self.root / "phrasematcher"
        header = ["PMID", "Sentence_ID", "Trait_ID", "Standard_Name",
                  "Start", "End", "Matched_Text", "Sentence_Text"]
        for group in stats.GROUPS:
            export = self.oger / "dataset" / group / "timestamp" / "pubtator"
            export.mkdir(parents=True)
            for sid, (pmid, text, year) in self.corpus.items():
                lines = ["{}|x|{}\n".format(sid, text)]
                if sid != "2_01":
                    lines += ["{}\t0\t2\tG1\tgene\tOryzaGeneID:1\n".format(sid),
                              "{}\t0\t1\tG\tgene\tSupplementary_geneID:2\n".format(sid)]
                    if group == "go":
                        lines.append("{}\t11\t17\tgrowth\tbiological_process\tGO:1\n".format(sid))
                (export / (sid + ".txt")).write_text("".join(lines), encoding="utf-8")
            for tool, root in (("scispacy", self.sci), ("phrasematcher", self.phrase)):
                folder = ("scispacy_" + group + "_result" if tool == "scispacy"
                          else "Rice-" + group.upper() + "-annotation-dir")
                (root / folder).mkdir(parents=True)
                for year in (2025, 2026):
                    name = ("{}_filtered_sent_result.tsv".format(year) if tool == "scispacy"
                            else "Rice.{}.sent.tsv".format(year))
                    with (root / folder / name).open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.writer(handle, delimiter="\t")
                        writer.writerow(header)
                        if group == "go":
                            sid = "1_01" if year == 2025 else "3_01"
                            pmid, text, _ = self.corpus[sid]
                            writer.writerow([pmid, sid, "GO:1", "growth", 11, 17, "growth", text])

    def args(self):
        return stats.build_parser().parse_args([
            "--sentence-file", str(self.sentences), "--year-map", str(self.year_map),
            "--oger-root", str(self.oger), "--scispacy-root", str(self.sci),
            "--phrase-root", str(self.phrase), "--oger-dict-dir", str(self.dicts),
            "--output-dir", str(self.root / "out")])

    def test_counts_sources_years_and_empty_sentences(self):
        stats.run(self.args())
        report = json.loads((self.root / "out" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(report["sentence_counts"]["input_sentences"], 3)
        self.assertEqual(report["sentence_counts"]["unannotated_sentences"], 1)
        self.assertEqual(report["by_year"]["2026"]["gene_sentences"], 1)
        gene = next(row for row in report["annotation_counts"]
                    if row["tool"] == "oger" and row["category"] == "gene")
        self.assertEqual((gene["input_annotation_rows"], gene["unique_mentions"],
                          gene["duplicates_collapsed"]), (20, 4, 16))
        self.assertEqual(report["gene_sources"]["Oryzabase"]["unique_mentions"], 2)
        self.assertEqual(report["gene_sources"]["Supplementary"]["unique_mentions"], 2)
        self.assertEqual(report["merged_unique_mentions"], 6)
        records = [json.loads(line) for line in
                   (self.root / "out" / "all_sentences_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
        gene_record = next(row for row in records if row["sent_id"] == "1_01")
        self.assertFalse(gene_record["is_strict_reliable"])
        self.assertTrue(gene_record["non_gene_categories_have_consensus"])
        self.assertEqual(gene_record["PMID"], "1")
        self.assertEqual(gene_record["annotations"]["oger"][1]["Normalization"], "Gene One")
        self.assertEqual(len(gene_record["merged_annotations"][-1]["tools"]), 3)
        multi = (self.root / "out" / "multi_entity_sentences_2025-2026.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(multi), 2)  # Single-tool genes are not discarded.

    def test_missing_file_and_mixed_runs_are_errors(self):
        duplicate = self.oger / "dataset" / "co" / "another_run" / "pubtator"
        duplicate.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "五轮"):
            stats.run(self.args())

    def test_missing_annual_file_is_an_error(self):
        empty = self.root / "empty"
        empty.mkdir()
        args = self.args()
        args.phrase_root = empty
        with self.assertRaisesRegex(ValueError, "缺少标注结果"):
            stats.run(args)

    def test_repeated_gene_at_different_offsets_is_not_collapsed(self):
        corpus = {"s": {"PMID": "1", "year": 2025, "text": "G1 G1"}}
        collector = stats.Collector(corpus, {"s"}, {})
        for _ in range(5):
            collector.add("oger", "s", 0, 2, "G1", "gene", "OryzaGeneID:1")
            collector.add("oger", "s", 3, 5, "G1", "gene", "OryzaGeneID:1")
        self.assertEqual(collector.raw[("oger", "gene")], 10)
        self.assertEqual(len(collector.annotations["s"]), 2)

    def test_missing_sentence_and_wrong_offsets_are_errors(self):
        path = self.oger / "dataset" / "co" / "timestamp" / "pubtator" / "1_01.txt"
        self.assertEqual(path.resolve().relative_to(self.root.resolve()).parts[0], "oger")
        path.unlink()
        with self.assertRaisesRegex(ValueError, "缺少"):
            stats.run(self.args())
        path.write_text("1_01|x|G1 affects growth.\n1_01\t0\t3\tG1\tgene\tOryzaGeneID:1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "字符位置"):
            stats.run(self.args())

    def test_empty_oger_export_keeps_sentence_in_denominator(self):
        for group in stats.GROUPS:
            path = self.oger / "dataset" / group / "timestamp" / "pubtator" / "2_01.txt"
            path.write_text("", encoding="utf-8")
        stats.run(self.args())
        report = json.loads((self.root / "out" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(report["sentence_counts"]["input_sentences"], 3)
        self.assertEqual(report["sentence_counts"]["unannotated_sentences"], 1)
        self.assertEqual(report["empty_oger_files_by_pass"], {g: 1 for g in stats.GROUPS})

    def test_conflicting_names_retained_without_arbitrary_mapping(self):
        corpus = {"s": {"PMID": "1", "year": 2025, "text": "growth"}}
        collector = stats.Collector(corpus, {"s"}, {})
        collector.add("scispacy", "s", 0, 6, "growth", "go", "GO:1", "growth")
        collector.add("phrasematcher", "s", 0, 6, "growth", "go", "GO:1", "other name")
        record = stats.make_sentence_record("s", corpus["s"], collector.annotations["s"])
        entry = record["merged_annotations"][0]
        self.assertEqual(entry["Normalization"], "")
        self.assertEqual(entry["standard_names"], ["growth", "other name"])

    def test_check_only_writes_nothing_and_reuse_is_rejected(self):
        args = self.args()
        args.check_only = True
        stats.run(args)
        self.assertFalse(args.output_dir.exists())
        args.check_only = False
        args.output_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "已存在"):
            stats.run(args)


if __name__ == "__main__":
    unittest.main()
