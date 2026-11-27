#!/usr/bin/env python3
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""Summarize one RiceMind three-tool batch without modifying annotations.

Python 3.8+, standard library only. Read the sentence TSV and year map as the
corpus of record. OGER must contain exactly one PubTator export for each of the
five passes; TSV tools must contain one file per selected year and dictionary.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from ricemind_config import BASE_DIR, CLEANED_OUTPUT_ROOT, OGER_DICT_DIR, OGER_INPUT_DIR, RESULTS_DIR

GROUPS = ("co", "go", "to", "rto", "variety")
TOOLS = ("oger", "scispacy", "phrasematcher")
DICT_NAMES = ("oryzabase_gene", "supplementary_gene") + GROUPS


def read_corpus(sentence_file, year_map, years):
    year_by_sid = {}
    with year_map.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not {"Sentence_ID", "Year"} <= set(reader.fieldnames or []):
            raise ValueError("年份映射缺少 Sentence_ID / Year 列")
        for row in reader:
            sid, year = row["Sentence_ID"], int(row["Year"])
            if sid in year_by_sid and year_by_sid[sid] != year:
                raise ValueError("同一句子存在冲突年份: " + sid)
            year_by_sid[sid] = year
    corpus = {}
    with sentence_file.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t", 2)
            if len(parts) != 3 or not all(parts):
                raise ValueError("句子 TSV 第 {} 行格式错误".format(number))
            pmid, sid, text = parts
            if sid not in year_by_sid:
                raise ValueError("缺少句子年份: " + sid)
            if sid in corpus:
                raise ValueError("输入句子 ID 重复，请先核查: " + sid)
            corpus[sid] = {"PMID": pmid, "text": text, "year": year_by_sid[sid]}
    selected = {sid for sid, row in corpus.items() if row["year"] in years}
    if not selected:
        raise ValueError("指定年份内没有输入句子")
    return corpus, selected


def gene_source(entity_id):
    if entity_id.startswith("OryzaGeneID:"):
        return "Oryzabase"
    if entity_id.startswith("Supplementary_geneID:"):
        return "Supplementary"
    return "Other"


def entity_group(entity_id, entity_type, pass_group):
    if entity_type.casefold() == "gene":
        return "gene"
    if entity_type.casefold() == "variety":
        return "variety"
    for prefix, group in (("CO_", "co"), ("GO:", "go"), ("TO:", "to"), ("RTO:", "rto")):
        if entity_id.startswith(prefix):
            return group
    if pass_group in GROUPS:
        return pass_group
    raise ValueError("无法判断实体类别: {} / {}".format(entity_type, entity_id))


def broad_category(group):
    return {"gene": "Gene", "variety": "Variety"}.get(group, "Phenotype")


def load_standard_names(dict_root):
    names = defaultdict(set)
    for name in DICT_NAMES:
        path = dict_root / (name + "_oger_dict.tsv")
        if not path.is_file():
            subdir = "genes" if name.endswith("_gene") else "ontology"
            path = dict_root / subdir / (name + "_oger_dict.tsv")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) != 6:
                    raise ValueError("{}:{} 必须是六列 OGER 词典".format(path, number))
                group = entity_group(parts[2], parts[5], name)
                if parts[4].strip():
                    names[(group, parts[2])].add(parts[4].strip())
    return names


def discover_files(oger_root, scispacy_root, phrase_root, years):
    exports = defaultdict(list)
    for path in sorted(oger_root.rglob("pubtator")):
        if path.is_dir():
            exports[path.parent.parent.name.casefold()].append(path)
    if set(exports) != set(GROUPS) or any(len(paths) != 1 for paths in exports.values()):
        raise ValueError(
            "OGER 根目录应只包含一个数据集的五轮结果，每轮恰好一个 pubtator 目录；"
            "实际: " + str({k: len(v) for k, v in exports.items()})
        )
    oger_files = {}
    for group in GROUPS:
        oger_files[group] = sorted(exports[group][0].glob("*.txt"))
        if not oger_files[group]:
            raise ValueError("OGER 导出为空: " + str(exports[group][0]))
    tsv_files = []
    for tool, root in (("scispacy", scispacy_root), ("phrasematcher", phrase_root)):
        for group in GROUPS:
            folder = ("scispacy_" + group + "_result" if tool == "scispacy"
                      else "Rice-" + group.upper() + "-annotation-dir")
            for year in years:
                filename = ("{}_filtered_sent_result.tsv".format(year) if tool == "scispacy"
                            else "Rice.{}.sent.tsv".format(year))
                path = root / folder / filename
                if not path.is_file():
                    raise ValueError("缺少标注结果: " + str(path))
                tsv_files.append((tool, group, year, path))
    return oger_files, tsv_files


class Collector:
    def __init__(self, corpus, selected, standard_names):
        self.corpus = corpus
        self.selected = selected
        self.standard_names = standard_names
        self.annotations = defaultdict(dict)
        self.raw = Counter()
        self.empty_oger_files = Counter()

    def check_sentence(self, sid, text=None, pmid=None, year=None):
        if sid not in self.corpus:
            raise ValueError("结果包含输入中不存在的句子: " + sid)
        original = self.corpus[sid]
        if text is not None and text != original["text"]:
            raise ValueError("结果与输入句子文本不一致: " + sid)
        if pmid is not None and pmid != original["PMID"]:
            raise ValueError("结果 PMID 与输入不一致: " + sid)
        if year is not None and year != original["year"]:
            raise ValueError("结果文件年份与句子年份不一致: " + sid)

    def add(self, tool, sid, start, end, matched, group, entity_id, standard=""):
        self.check_sentence(sid)
        start, end = int(start), int(end)
        text = self.corpus[sid]["text"]
        if not entity_id or not (0 <= start < end <= len(text)) or text[start:end] != matched:
            raise ValueError("实体 ID 或字符位置不匹配: {} {}:{} {!r}".format(sid, start, end, matched))
        if sid not in self.selected:
            return
        self.raw[(tool, group)] += 1
        # The tool/pass is deliberately absent from the identity key.
        key = (start, end, group, entity_id)
        entry = self.annotations[sid].get(key)
        if entry is None:
            entry = {"start": start, "end": end, "id": entity_id,
                     "cat": broad_category(group), "category": group,
                     "Matched_Text": matched, "tools": set(), "standard_names": set()}
            self.annotations[sid][key] = entry
        entry["tools"].add(tool)
        if standard:
            entry["standard_names"].add(standard)
        if tool == "oger":
            entry["standard_names"].update(self.standard_names.get((group, entity_id), ()))


def read_oger(files, collector):
    coverage = {}
    total_files = sum(len(paths) for paths in files.values())
    done = 0
    for group, paths in files.items():
        seen = set()
        all_seen = set()
        for path in paths:
            records = set()
            with path.open(encoding="utf-8-sig") as handle:
                for number, line in enumerate(handle, 1):
                    line = line.rstrip("\r\n")
                    if not line:
                        continue
                    if "\t" not in line and "|x|" in line:
                        sid, text = line.split("|x|", 1)
                        collector.check_sentence(sid, text=text)
                        if sid in all_seen:
                            raise ValueError("同一 OGER 轮次重复句子: " + sid)
                        all_seen.add(sid)
                        records.add(sid)
                        if sid in collector.selected:
                            seen.add(sid)
                        continue
                    parts = line.split("\t")
                    if len(parts) != 6:
                        raise ValueError("{}:{} 非预期 PubTator 行".format(path, number))
                    sid, start, end, matched, label, entity_id = parts
                    if sid not in records:
                        raise ValueError("{}:{} 标注前缺少句子文本".format(path, number))
                    category = entity_group(entity_id, label, group)
                    collector.add("oger", sid, start, end, matched, category, entity_id)
            if not records:
                if path.stat().st_size:
                    raise ValueError("非空 OGER 文件没有句子记录: " + str(path))
                # OGER can create an empty export for an input sentence. Recover
                # its identity from the filename, and keep it visible in the audit.
                sid = path.stem
                collector.check_sentence(sid)
                if sid in all_seen:
                    raise ValueError("同一 OGER 轮次重复句子: " + sid)
                all_seen.add(sid)
                if sid in collector.selected:
                    seen.add(sid)
                    collector.empty_oger_files[group] += 1
            done += 1
            if done % 20000 == 0:
                print("[INFO] OGER files: {:,}/{:,}".format(done, total_files), flush=True)
        missing = collector.selected - seen
        if missing:
            raise ValueError("OGER {} 缺少 {} 条输入句子，例如 {}".format(
                group, len(missing), sorted(missing)[:3]))
        coverage[group] = len(seen)
    return coverage


def read_tsv(files, collector):
    fields = {"PMID", "Sentence_ID", "Trait_ID", "Standard_Name",
              "Start", "End", "Matched_Text", "Sentence_Text"}
    for tool, group, year, path in files:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not fields <= set(reader.fieldnames or []):
                raise ValueError("标注 TSV 缺少必要列: " + str(path))
            for row in reader:
                if None in row or any(row.get(f) is None for f in fields):
                    raise ValueError("标注 TSV 行格式错误: " + str(path))
                sid = row["Sentence_ID"]
                collector.check_sentence(sid, row["Sentence_Text"], row["PMID"], year)
                collector.add(tool, sid, row["Start"], row["End"], row["Matched_Text"],
                              group, row["Trait_ID"], row["Standard_Name"])


def make_sentence_record(sid, original, entries):
    by_tool = {tool: [] for tool in TOOLS}
    merged = []
    consensus_categories = set()
    for key in sorted(entries):
        entry = entries[key]
        names = sorted(entry["standard_names"])
        tools = sorted(entry["tools"])
        annotation = {k: v for k, v in entry.items() if k not in ("tools", "standard_names")}
        annotation.update(Normalization=names[0] if len(names) == 1 else "",
                          standard_names=names, tools=tools)
        if annotation["category"] == "gene":
            annotation["gene_source"] = gene_source(annotation["id"])
        merged.append(annotation)
        for tool in tools:
            by_tool[tool].append(dict(annotation, tool=tool))
        if len(tools) >= 2:
            consensus_categories.add(entry["cat"])
    categories = sorted({entry["cat"] for entry in merged})
    non_gene = set(categories) - {"Gene"}
    return dict(original, sent_id=sid, annotations=by_tool, merged_annotations=merged,
                categories=categories, has_gene="Gene" in categories,
                is_multi_entity=len(categories) >= 2,
                # Retain the legacy flag as a descriptive statistic, never as a filter.
                is_strict_reliable=(len(categories) >= 2 and set(categories) <= consensus_categories),
                non_gene_categories_have_consensus=bool(non_gene) and non_gene <= consensus_categories)


def write_reports(output_dir, collector, years, manifest, coverage):
    unique_counts, group_sentences, group_ids = Counter(), defaultdict(set), defaultdict(set)
    overlaps, gene_terms, year_summary = Counter(), {}, {}
    for year in years:
        year_summary[str(year)] = dict(input_sentences=0, annotated_sentences=0,
                                      unannotated_sentences=0, multi_category_sentences=0,
                                      gene_sentences=0, gene_phenotype_sentences=0,
                                      legacy_strict_sentences=0)
    missing_names = ambiguous_names = merged_count = 0
    output_dir.mkdir(parents=True, exist_ok=False)
    with ExitStack() as stack:
        all_handle = stack.enter_context((output_dir / "all_sentences_annotations.jsonl").open("w", encoding="utf-8"))
        multi_handle = stack.enter_context((output_dir / "multi_entity_sentences_{}-{}.jsonl".format(
            years[0], years[-1])).open("w", encoding="utf-8"))
        for sid in sorted(collector.selected, key=lambda s: (collector.corpus[s]["year"], s)):
            original = collector.corpus[sid]
            record = make_sentence_record(sid, original, collector.annotations.get(sid, {}))
            json_line = json.dumps(record, ensure_ascii=False) + "\n"
            all_handle.write(json_line)
            if record["is_multi_entity"]:
                multi_handle.write(json_line)
            yr = year_summary[str(original["year"])]
            yr["input_sentences"] += 1
            yr["annotated_sentences"] += bool(record["merged_annotations"])
            yr["unannotated_sentences"] += not record["merged_annotations"]
            yr["multi_category_sentences"] += record["is_multi_entity"]
            yr["gene_sentences"] += record["has_gene"]
            yr["gene_phenotype_sentences"] += {"Gene", "Phenotype"} <= set(record["categories"])
            yr["legacy_strict_sentences"] += record["is_strict_reliable"]
            for entry in record["merged_annotations"]:
                merged_count += 1
                missing_names += not entry["standard_names"]
                ambiguous_names += len(entry["standard_names"]) > 1
                group, entity_id = entry["category"], entry["id"]
                overlaps[(group, "+".join(entry["tools"]))] += 1
                for tool in entry["tools"] + ["union"]:
                    unique_counts[(tool, group)] += 1
                    group_sentences[(tool, group)].add(sid)
                    group_ids[(tool, group)].add(entity_id)
                if group == "gene":
                    term_key = (entry["gene_source"], entity_id, entry["Matched_Text"].casefold())
                    item = gene_terms.setdefault(term_key, dict(
                        mentions=0, sentences=set(), pmids=set(), names=set(),
                        example_sid=sid, example_text=original["text"]))
                    item["mentions"] += 1
                    item["sentences"].add(sid)
                    item["pmids"].add(original["PMID"])
                    item["names"].update(entry["standard_names"])
    table_rows = []
    for tool in TOOLS + ("union",):
        for group in ("gene",) + GROUPS:
            key = (tool, group)
            raw = sum(collector.raw[(t, group)] for t in TOOLS) if tool == "union" else collector.raw[key]
            table_rows.append(dict(tool=tool, category=group, input_annotation_rows=raw,
                                   unique_mentions=unique_counts[key],
                                   duplicates_collapsed=raw - unique_counts[key],
                                   matched_sentences=len(group_sentences[key]),
                                   distinct_ids=len(group_ids[key])))
    write_table(output_dir / "annotation_counts.tsv", list(table_rows[0]), table_rows)
    overlap_rows = [dict(category=k[0], tools=k[1], unique_mentions=v)
                    for k, v in sorted(overlaps.items())]
    write_table(output_dir / "tool_overlap.tsv", ["category", "tools", "unique_mentions"], overlap_rows)
    gene_rows = []
    for (source, entity_id, matched), item in sorted(gene_terms.items(), key=lambda kv: (-kv[1]["mentions"], kv[0])):
        gene_rows.append(dict(gene_source=source, gene_id=entity_id, matched_text_lower=matched,
                              standard_names="|".join(sorted(item["names"])),
                              unique_mentions=item["mentions"], matched_sentences=len(item["sentences"]),
                              articles=len(item["pmids"]), example_sentence_id=item["example_sid"],
                              example_sentence_text=item["example_text"]))
    gene_fields = ["gene_source", "gene_id", "matched_text_lower", "standard_names", "unique_mentions",
                   "matched_sentences", "articles", "example_sentence_id", "example_sentence_text"]
    write_table(output_dir / "gene_name_frequency.tsv", gene_fields, gene_rows)
    gene_summary = {}
    for source in ("Oryzabase", "Supplementary", "Other"):
        terms = [(k, v) for k, v in gene_terms.items() if k[0] == source]
        gene_summary[source] = dict(
            unique_mentions=sum(v["mentions"] for k, v in terms),
            distinct_ids=len({k[1] for k, v in terms}),
            matched_sentences=len({sid for k, v in terms for sid in v["sentences"]}),
            articles=len({pmid for k, v in terms for pmid in v["pmids"]}))
    totals = {key: sum(row[key] for row in year_summary.values())
              for key in next(iter(year_summary.values()))}
    summary = dict(
        created_at=datetime.now().astimezone().isoformat(), years=years, inputs=manifest,
        sentence_counts=totals, by_year=year_summary, oger_pass_sentence_coverage=coverage,
        empty_oger_files_by_pass={g: collector.empty_oger_files[g] for g in GROUPS},
        annotation_counts=table_rows, gene_sources=gene_summary,
        merged_unique_mentions=merged_count,
        mentions_without_standard_name=missing_names,
        mentions_with_conflicting_standard_names=ambiguous_names,
        notes=[
            "This run summarizes the supplied results; it does not apply blacklist rules or rerun annotation.",
            "Mentions are deduplicated by sentence ID, start, end, category and entity ID.",
            "All five OGER passes count as one tool. BioC JSON is not read.",
            "All input sentences, including sentences with no remaining annotations, are included.",
            "Empty OGER files are mapped by filename and reported separately. Counts alone cannot distinguish no hits from upstream truncation; check annotation completion logs.",
            "Distinct IDs are dictionary identifiers, not validated counts of biological genes.",
            "The legacy is_strict_reliable flag is retained for reference and never used to discard genes.",
            "Tool agreement does not establish annotation accuracy or biological relationships.",
            "Conflicting standard names are retained as a list; Normalization is empty when ambiguous.",
            "Year labels come from the supplied map; month-level publication dates are not verified.",
        ])
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("[INFO] 输入句子: {:,}; 有标注: {:,}; 无标注: {:,}".format(
        totals["input_sentences"], totals["annotated_sentences"], totals["unannotated_sentences"]))
    print("[INFO] 合并去重实体提及: {:,}; 含基因句子: {:,}; 基因+性状/功能句子: {:,}".format(
        merged_count, totals["gene_sentences"], totals["gene_phenotype_sentences"]))
    for source, stats in gene_summary.items():
        print("[INFO] {}: 去重提及={:,}, 不同ID={:,}, 命中句子={:,}".format(
            source, stats["unique_mentions"], stats["distinct_ids"], stats["matched_sentences"]))
    print("[INFO] 统计完成: " + str(output_dir))


def write_table(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_parser():
    parser = argparse.ArgumentParser(description="统计同批次三工具标注，去重 OGER 五轮并保留句子及基因来源。")
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--sentence-file", type=Path, help="PMID、Sentence_ID、Sentence_Text 三列 TSV")
    parser.add_argument("--year-map", type=Path, help="Sentence_ID、Year 两列表")
    parser.add_argument("--cleaned-root", type=Path, default=CLEANED_OUTPUT_ROOT / "keyword_filtered")
    parser.add_argument("--oger-root", type=Path)
    parser.add_argument("--scispacy-root", type=Path)
    parser.add_argument("--phrase-root", type=Path)
    parser.add_argument("--oger-dict-dir", type=Path, default=OGER_DICT_DIR)
    parser.add_argument("--output-dir", type=Path, help="新建输出目录；已存在则报错以保护旧统计")
    parser.add_argument("--check-only", action="store_true", help="完整校验输入和标注，不写出统计")
    return parser


def run(args):
    if args.start_year > args.end_year:
        raise ValueError("开始年份不能晚于结束年份")
    years = list(range(args.start_year, args.end_year + 1))
    label = "{}-{}_keyword".format(args.start_year, args.end_year)
    sentence_file = args.sentence_file or OGER_INPUT_DIR / "keyword_filtered" / (label + "_filtered_sent.tsv")
    year_map = args.year_map or OGER_INPUT_DIR / "keyword_filtered" / (label + "_sentence_year_map.tsv")
    oger_root = args.oger_root or args.cleaned_root / "oger"
    scispacy_root = args.scispacy_root or args.cleaned_root / "scispacy"
    phrase_root = args.phrase_root or args.cleaned_root / "phrasematcher"
    output_dir = args.output_dir or RESULTS_DIR / "statistics" / "keyword_filtered" / (
        datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid()))
    for path in (sentence_file, year_map):
        if not path.is_file():
            raise ValueError("缺少输入: " + str(path))
    for path in (oger_root, scispacy_root, phrase_root, args.oger_dict_dir):
        if not path.is_dir():
            raise ValueError("缺少目录: " + str(path))
    if not args.check_only and output_dir.exists():
        raise ValueError("输出目录已存在，请指定新的 --output-dir: " + str(output_dir))
    corpus, selected = read_corpus(sentence_file, year_map, years)
    print("[INFO] 目标句子: {:,}; 年份: {}-{}".format(len(selected), years[0], years[-1]), flush=True)
    oger_files, tsv_files = discover_files(oger_root, scispacy_root, phrase_root, years)
    print("[INFO] OGER: {:,} 个 PubTator 文件；其他工具: {} 个 TSV".format(
        sum(map(len, oger_files.values())), len(tsv_files)), flush=True)
    collector = Collector(corpus, selected, load_standard_names(args.oger_dict_dir))
    coverage = read_oger(oger_files, collector)
    read_tsv(tsv_files, collector)
    if args.check_only:
        print("[INFO] 校验通过；未写入统计文件。")
        return
    manifest = {name: str(path.resolve()) for name, path in (
        ("sentences", sentence_file), ("year_map", year_map), ("oger_root", oger_root),
        ("scispacy_root", scispacy_root), ("phrase_root", phrase_root),
        ("oger_dict_dir", args.oger_dict_dir))}
    manifest["file_counts"] = dict(oger=sum(map(len, oger_files.values())),
                                  scispacy=sum(t == "scispacy" for t, g, y, p in tsv_files),
                                  phrasematcher=sum(t == "phrasematcher" for t, g, y, p in tsv_files))
    write_reports(output_dir, collector, years, manifest, coverage)


def main():
    args = build_parser().parse_args()
    try:
        run(args)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print("[ERROR] " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
