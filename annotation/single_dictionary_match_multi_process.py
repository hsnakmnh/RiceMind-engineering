# Adapted from separately author-provided Pipeline source.
# Original header: @Author: yao; Created on 23/01/2023 15:16.
# Redistribution scope: docs/ATTRIBUTION.md
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RiceMind's self-contained PhraseMatcher annotation stage.

This file is adapted from the generic ``single_dictionary_match_multi_process.py``
script used by the original pipeline.  The original script assumed the input
columns were ``Sentence_ID, PMID, Sentence`` and loaded the unrelated
``en_core_web_md`` model.  RiceMind sentence files use
``PMID, Sentence_ID, Sentence``.  This adapter uses the RiceMind column order,
the repository dictionaries, and the same eight-column result format as the
SciSpacy scripts, so it can run without the external Pipeline checkout.

PhraseMatcher is an exact token phrase lookup.  It does not perform model-based
NER; a blank English spaCy tokenizer is therefore sufficient and is the
default.  A spaCy model can be supplied with ``--model`` when matching the
tokenisation of another stage is required.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import spacy
from spacy.matcher import PhraseMatcher


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ricemind_config import DICT_DIR, PHRASE_OUTPUT_ROOT, SENTENCE_DIR


CATEGORIES: Tuple[str, ...] = ("co", "go", "to", "rto", "variety")
OUTPUT_FOLDERS = {
    "co": "Rice-CO-annotation-dir",
    "go": "Rice-GO-annotation-dir",
    "to": "Rice-TO-annotation-dir",
    "rto": "Rice-RTO-annotation-dir",
    "variety": "Rice-VARIETY-annotation-dir",
}


DictionaryEntry = Tuple[str, str]


def _is_header(row: Sequence[str]) -> bool:
    """Recognise the header present in the author's variety dictionary."""

    if len(row) < 2:
        return False
    first = row[0].strip().casefold()
    second = row[1].strip().casefold()
    return first in {"id", "trait_id", "variety_id", "go_id"} and second in {
        "name",
        "standard_name",
        "variety_name",
    }


def read_dictionary(
    dictionary_path: Path,
    nlp,
    *,
    include_standard_name: bool = True,
    min_term_length: int = 3,
) -> Tuple[Dict[str, DictionaryEntry], List[object], int]:
    """Read a RiceMind three-column dictionary and build matcher patterns.

    The columns are ``ID<TAB>standard name<TAB>synonym1|synonym2``.  Empty
    terms and the optional variety header are ignored.  If the same term maps
    to multiple IDs, the first mapping is retained deterministically and the
    number of such collisions is returned for reporting.
    """

    term_to_entry: Dict[str, DictionaryEntry] = {}
    term_to_surface: Dict[str, str] = {}
    collisions = 0

    with dictionary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if not row or not any(cell.strip() for cell in row):
                continue
            if _is_header(row):
                continue
            if len(row) < 2:
                print(
                    f"[WARN] {dictionary_path.name}:{line_number}: "
                    "fewer than two tab-separated columns; skipped.",
                    file=sys.stderr,
                )
                continue

            trait_id = row[0].strip()
            standard_name = row[1].strip()
            synonyms = row[2] if len(row) >= 3 else ""
            if not trait_id or not standard_name:
                continue

            terms: List[str] = []
            if include_standard_name:
                terms.append(standard_name)
            terms.extend(synonym.strip() for synonym in synonyms.split("|"))

            for term in terms:
                if len(term) < min_term_length:
                    continue
                key = term.casefold()
                entry = (trait_id, standard_name)
                previous = term_to_entry.get(key)
                if previous is not None:
                    if previous != entry:
                        collisions += 1
                    continue
                term_to_entry[key] = entry
                term_to_surface[key] = term

    patterns = [nlp.make_doc(term_to_surface[key]) for key in term_to_entry]
    return term_to_entry, patterns, collisions


def _iter_input_files(input_dir: Path, input_file: Optional[Path]) -> List[Path]:
    if input_file is not None:
        return [input_file]
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and (path.name.endswith(".sent.txt") or path.name.endswith(".txt"))
    )


def _sentence_batches(
    input_path: Path, batch_size: int
) -> Iterator[List[Tuple[str, str, str]]]:
    """Yield ``(pmid, sentence_id, text)`` batches in RiceMind order."""

    batch: List[Tuple[str, str, str]] = []
    with input_path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                print(
                    f"[WARN] {input_path.name}:{line_number}: malformed line; skipped.",
                    file=sys.stderr,
                )
                continue
            pmid, sentence_id, text = (part.strip() for part in parts)
            if sentence_id.casefold() in {"sentence_id", "sentid"}:
                continue
            if not pmid or not sentence_id or not text:
                continue
            batch.append((pmid, sentence_id, text))
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def _make_nlp(model: str):
    if not model or model.casefold() in {"blank", "blank:en"}:
        return spacy.blank("en")
    return spacy.load(
        model,
        disable=[
            "ner",
            "parser",
            "tagger",
            "lemmatizer",
            "transformer",
            "attribute_ruler",
        ],
    )


def _add_patterns(matcher: PhraseMatcher, patterns: Sequence[object]) -> None:
    # spaCy 3.x uses matcher.add(name, patterns); the fallback keeps the file
    # usable with the older API used by the original script.
    try:
        matcher.add("RiceMind", list(patterns))
    except TypeError:
        matcher.add("RiceMind", None, *patterns)


def _output_name(input_path: Path) -> str:
    match = re.search(r"20\d{2}", input_path.stem)
    if match:
        return f"Rice.{match.group(0)}.sent.tsv"
    return f"{input_path.stem}.tsv"


def annotate_file(
    input_path: Path,
    output_path: Path,
    nlp,
    matcher: PhraseMatcher,
    term_to_entry: Dict[str, DictionaryEntry],
    *,
    batch_size: int,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_count = 0

    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "PMID",
                "Sentence_ID",
                "Trait_ID",
                "Standard_Name",
                "Start",
                "End",
                "Matched_Text",
                "Sentence_Text",
            ]
        )

        for batch in _sentence_batches(input_path, batch_size):
            texts = [record[2] for record in batch]
            for (pmid, sentence_id, raw_text), doc in zip(batch, nlp.pipe(texts, batch_size=batch_size)):
                for _match_id, start, end in matcher(doc):
                    span = doc[start:end]
                    entry = term_to_entry.get(span.text.casefold().strip())
                    if entry is None:
                        # This should be rare (e.g. a tokenizer normalisation
                        # difference), but preserve the row rather than drop it.
                        trait_id, standard_name = "NoNorm", span.text
                    else:
                        trait_id, standard_name = entry
                    writer.writerow(
                        [
                            pmid,
                            sentence_id,
                            trait_id,
                            standard_name,
                            span.start_char,
                            span.end_char,
                            span.text,
                            raw_text,
                        ]
                    )
                    annotation_count += 1
    return annotation_count


def run(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).expanduser()
    input_file = Path(args.input_file).expanduser() if args.input_file else None
    output_root = Path(args.output_root).expanduser()
    dict_dir = Path(args.dict_dir).expanduser()

    if input_file is not None:
        if not input_file.is_file():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
    elif not input_dir.is_dir():
        raise NotADirectoryError(f"输入目录不存在: {input_dir}")

    dictionary_paths = {
        category: Path(args.dictionary.get(category, dict_dir / f"{category}-dict.tsv"))
        for category in CATEGORIES
    }
    for category, path in dictionary_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{category} 词典不存在: {path}")

    input_files = _iter_input_files(input_dir, input_file)
    if not input_files:
        raise FileNotFoundError(f"输入目录中没有 .txt 或 .sent.txt 文件: {input_dir}")

    print(f"[INFO] PhraseMatcher 输入: {input_file or input_dir}")
    print(f"[INFO] PhraseMatcher 输出: {output_root}")
    print(f"[INFO] 输入文件数: {len(input_files)}")
    print(f"[INFO] 分词模型: {args.model or 'blank:en'}")

    if args.dry_run:
        for category in CATEGORIES:
            print(
                f"[DRY-RUN] {category}: {dictionary_paths[category]} -> "
                f"{output_root / OUTPUT_FOLDERS[category]}"
            )
        return 0

    nlp = _make_nlp(args.model)
    total_annotations = 0
    total_files = 0

    for category in CATEGORIES:
        dictionary_path = dictionary_paths[category]
        term_to_entry, patterns, collisions = read_dictionary(
            dictionary_path,
            nlp,
            include_standard_name=not args.synonyms_only,
            min_term_length=args.min_term_length,
        )
        matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        _add_patterns(matcher, patterns)
        if collisions:
            print(
                f"[WARN] {category}: {collisions} 个重复词条映射到多个 ID；已保留首次映射。",
                file=sys.stderr,
            )
        print(f"[INFO] {category}: 加载 {len(patterns):,} 个匹配词条。")

        category_dir = output_root / OUTPUT_FOLDERS[category]
        for input_path in input_files:
            output_path = category_dir / _output_name(input_path)
            if output_path.exists() and args.pass_existing:
                print(f"[INFO] 跳过已存在文件: {output_path}")
                continue
            count = annotate_file(
                input_path,
                output_path,
                nlp,
                matcher,
                term_to_entry,
                batch_size=args.batch_size,
            )
            total_annotations += count
            total_files += 1
            print(f"[INFO] {category}/{input_path.name}: {count:,} 条实体 -> {output_path}")

    print(f"[INFO] PhraseMatcher 完成: files={total_files}, annotations={total_annotations:,}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RiceMind 三列词典的 PhraseMatcher 标注（PMID/Sentence_ID/Text 输入）。"
    )
    parser.add_argument("--input-dir", default=str(SENTENCE_DIR))
    parser.add_argument("--input-file", help="只处理一个句子 TSV 文件；与 --input-dir 二选一。")
    parser.add_argument("--output-root", default=str(PHRASE_OUTPUT_ROOT))
    parser.add_argument("--dict-dir", default=str(DICT_DIR / "annotation"))
    parser.add_argument("--model", default=os.environ.get("RICEMIND_PHRASE_MODEL", "blank"))
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--min-term-length", type=int, default=3)
    parser.add_argument(
        "--synonyms-only",
        action="store_true",
        help="严格复现原脚本：只使用第三列 synonyms，不把第二列 standard name 加入匹配。",
    )
    parser.add_argument("--pass-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(dictionary={})
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
