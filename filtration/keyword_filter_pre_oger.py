#!/usr/bin/env python3
"""Merge yearly sentence TSVs, apply RiceMind's keyword filter, and write OGER JSON.

This is an explicit pre-OGER adapter. It reuses the predicate from
keyword_filter.py while leaving that script's existing multi-entity JSONL
workflow unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from filtration.keyword_filter import is_valid_sentence
from ricemind_config import OGER_INPUT_DIR, SENTENCE_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "合并年度句子 TSV，复用 RiceMind 关键词规则筛句，"
            "输出一个 OGER txt_json 文件。"
        )
    )
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--input-dir", type=Path, default=SENTENCE_DIR)
    parser.add_argument(
        "--output-dir", type=Path, default=OGER_INPUT_DIR / "keyword_filtered"
    )
    parser.add_argument(
        "--dataset-label",
        help="输出文件名前缀；默认使用 START-END_keyword_filtered",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许覆盖同名的筛选输出文件",
    )
    return parser


def _write_json_record(handle, record: Dict[str, str], first: bool) -> bool:
    if not first:
        handle.write(",\n")
    json.dump(record, handle, ensure_ascii=False)
    return False


def filter_and_merge(
    input_dir: Path,
    output_dir: Path,
    years: List[int],
    dataset_label: str,
    force: bool = False,
) -> Tuple[Path, Path, Path, Path, Dict[str, object]]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_label):
        raise ValueError("dataset-label 只能包含英文字母、数字、点、下划线和连字符")
    if not years or years != sorted(set(years)):
        raise ValueError("年份必须递增且不能重复")

    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    input_files = [input_dir / f"{year}_filtered_sent.txt" for year in years]
    missing = [path for path in input_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "找不到年度句子文件：" + ", ".join(str(path) for path in missing)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_tsv = output_dir / f"{dataset_label}_filtered_sent.tsv"
    output_json = output_dir / f"{dataset_label}_filtered_sent.json"
    year_map = output_dir / f"{dataset_label}_sentence_year_map.tsv"
    stats_file = output_dir / f"{dataset_label}_filter_stats.json"
    outputs = [output_tsv, output_json, year_map, stats_file]
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "筛选输出已存在；为避免覆盖，请更换 --dataset-label 或显式加 --force："
            + ", ".join(str(path) for path in existing)
        )

    temp_outputs = [path.with_name(f".{path.name}.tmp-{os.getpid()}") for path in outputs]
    total = 0
    malformed = 0
    retained = 0
    dropped = Counter()
    retained_by_tag = Counter()
    retained_by_year = Counter()
    seen_ids: Set[str] = set()

    try:
        with ExitStack() as stack:
            tsv_out = stack.enter_context(
                temp_outputs[0].open("w", encoding="utf-8", newline="\n")
            )
            json_out = stack.enter_context(
                temp_outputs[1].open("w", encoding="utf-8", newline="\n")
            )
            map_out = stack.enter_context(
                temp_outputs[2].open("w", encoding="utf-8", newline="\n")
            )
            json_out.write("[\n")
            map_out.write("Sentence_ID\tYear\n")
            first_json_record = True

            for year, input_file in zip(years, input_files):
                with input_file.open(
                    "r", encoding="utf-8", errors="replace"
                ) as source:
                    for line_number, raw_line in enumerate(source, start=1):
                        line = raw_line.rstrip("\r\n")
                        if not line:
                            continue
                        fields = line.split("\t", 2)
                        if len(fields) != 3 or not fields[0] or not fields[1]:
                            malformed += 1
                            continue

                        pmid, sentence_id, text = fields
                        total += 1
                        if "\t" in text:
                            raise ValueError(
                                "句子文本含有制表符，无法安全写回 TSV："
                                f"{input_file}:{line_number}"
                            )
                        if sentence_id in seen_ids:
                            raise ValueError(
                                f"句子 ID 重复，已停止以避免重复标注：{sentence_id}"
                            )
                        seen_ids.add(sentence_id)

                        if len(text) < 20:
                            dropped["TooShort"] += 1
                            continue
                        if len(text) > 2000:
                            dropped["TooLong"] += 1
                            continue

                        valid, tag = is_valid_sentence(text)
                        if not valid:
                            dropped[tag] += 1
                            continue

                        tsv_out.write(f"{pmid}\t{sentence_id}\t{text}\n")
                        map_out.write(f"{sentence_id}\t{year}\n")
                        first_json_record = _write_json_record(
                            json_out,
                            {"id": sentence_id, "text": text},
                            first_json_record,
                        )
                        retained += 1
                        retained_by_year[str(year)] += 1
                        retained_by_tag[tag] += 1

            json_out.write("\n]\n")

        stats: Dict[str, object] = {
            "years": years,
            "input_files": [str(path) for path in input_files],
            "input_sentences": total,
            "malformed_lines": malformed,
            "retained_sentences": retained,
            "retention_rate": round(retained / total, 6) if total else 0,
            "retained_by_year": dict(retained_by_year),
            "retained_by_filter_tag": dict(retained_by_tag),
            "dropped_by_reason": dict(dropped),
            "outputs": {
                "combined_tsv": str(output_tsv),
                "oger_json": str(output_json),
                "sentence_year_map": str(year_map),
            },
        }
        with temp_outputs[3].open("w", encoding="utf-8", newline="\n") as stats_out:
            json.dump(stats, stats_out, ensure_ascii=False, indent=2)
            stats_out.write("\n")

        for temp_path, final_path in zip(temp_outputs, outputs):
            os.replace(temp_path, final_path)
    except Exception:
        for temp_path in temp_outputs:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return output_tsv, output_json, year_map, stats_file, stats


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.start_year > args.end_year:
        parser.error("--start-year 不能大于 --end-year")
    years = list(range(args.start_year, args.end_year + 1))
    label = args.dataset_label or f"{args.start_year}-{args.end_year}_keyword"

    try:
        output_tsv, output_json, year_map, stats_file, stats = filter_and_merge(
            args.input_dir,
            args.output_dir,
            years,
            label,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2

    print(f"[INFO] 输入句子: {stats['input_sentences']:,}")
    print(f"[INFO] 保留句子: {stats['retained_sentences']:,}")
    print(f"[INFO] 保留率: {stats['retention_rate']:.1%}")
    print(f"[INFO] 合并 TSV: {output_tsv}")
    print(f"[INFO] OGER JSON: {output_json}")
    print(f"[INFO] 年份映射: {year_map}")
    print(f"[INFO] 筛选统计: {stats_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
