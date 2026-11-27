#!/usr/bin/env python3
"""Convert PubTator text files into RiceMind sentence TSV files.

The Alterome PubTator output contains article-level records such as::

    PMID|t|Title
    PMID|a|Abstract
    PMID<TAB>start<TAB>end<TAB>mention<TAB>type<TAB>identifier

RiceMind's annotation scripts expect one sentence per line::

    PMID<TAB>Sentence_ID<TAB>Sentence_Text

This converter keeps abstract text by default, ignores the generic PubTator
annotation rows, deduplicates articles found through multiple query terms, and
writes files named ``YYYY_filtered_sent.txt``.  The output has no header
because the current SciSpacy scripts treat every line as data.  Article titles
can be included explicitly with ``--include-title``.

Exact month filtering requires a PMID-to-date map.  The map is a two-column
TSV file (``PMID<TAB>YYYY-MM-DD``).  PubTator's ``|t|``/``|a|`` records do not
contain publication dates, so the converter refuses to claim month-level
precision when date bounds are supplied without such a map.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import html
import os
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from ricemind_config import PUBTATOR_DIR, SENTENCE_DIR


YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
PASSAGE_RE = re.compile(r"^([^|\t]+)\|([ta])\|(.*)$")
SENTENCE_END_RE = re.compile(r"[.!?。！？]+")
HTML_TAG_RE = re.compile(r"\\?<[^>]+>")

# Common abbreviations in biomedical abstracts.  These are only used by the
# lightweight fallback segmenter; a full NLP sentence segmenter can be added
# later without changing the output format.
ABBREVIATIONS = {
    "e.g",
    "i.e",
    "etc",
    "vs",
    "fig",
    "figs",
    "dr",
    "mr",
    "mrs",
    "prof",
    "no",
    "approx",
    "ref",
    "refs",
    "st",
    "inc",
    "al",
    "u.s",
    "u.k",
}


def parse_year(path: Path) -> int:
    """Extract a four-digit year from an input filename."""

    match = YEAR_RE.search(path.name)
    if not match:
        raise ValueError(f"无法从文件名中识别年份: {path.name}")
    return int(match.group(1))


def clean_text(text: str) -> str:
    """Remove PubTator HTML markup and collapse whitespace."""

    text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    return " ".join(text.replace("\t", " ").replace("\r", " ").replace("\n", " ").split())


def _looks_like_abbreviation(text_before_period: str) -> bool:
    """Return whether the final token before a period is an abbreviation."""

    token_match = re.search(r"([A-Za-z][A-Za-z.]*)\.$", text_before_period)
    if not token_match:
        return False
    token = token_match.group(1).lower()
    return token in ABBREVIATIONS or (
        token.count(".") >= 1 and len(token.replace(".", "")) <= 3
    )


def _inside_unclosed_delimiter(text: str, start: int, end: int) -> bool:
    """Avoid splitting a bracketed heading such as ``[Heading. 2018]``."""

    fragment = text[start:end]
    for opening, closing in (("[", "]"), ("(", ")"), ("{", "}")):
        if fragment.count(opening) > fragment.count(closing):
            return True
    return False


def split_sentences(text: str) -> List[str]:
    """Split an abstract into readable sentences without extra dependencies.

    The splitter deliberately stays conservative around decimal numbers,
    abbreviations, and lower-case continuations.  It is intended to create a
    stable input for RiceMind's dictionary matchers; users can replace it with
    a SciSpacy sentence segmenter later if needed.
    """

    text = clean_text(text)
    if not text:
        return []

    sentences: List[str] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(text):
        end = match.end()
        if end < len(text) and not text[end].isspace():
            continue

        punctuation = match.group(0)
        if punctuation == ".":
            if _inside_unclosed_delimiter(text, start, match.end()):
                continue
            before = text[max(start, match.start() - 32) : match.start() + 1]
            if _looks_like_abbreviation(before):
                continue
            if match.start() > 0 and match.start() + 1 < len(text):
                if text[match.start() - 1].isdigit() and text[match.start() + 1].isdigit():
                    continue

        next_pos = end
        while next_pos < len(text) and text[next_pos].isspace():
            next_pos += 1

        # Require a plausible sentence start.  This avoids splitting on a
        # decimal or an inline citation followed by lower-case text.
        if next_pos < len(text) and not (
            text[next_pos].isupper()
            or text[next_pos].isdigit()
            or text[next_pos] in "([{\"'"
        ):
            continue

        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = next_pos

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def normalize_date(value: str) -> Optional[str]:
    """Normalize YYYY-MM-DD or YYYY/MM/DD to ISO format."""

    value = value.strip()
    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if not match:
        return None
    try:
        parsed = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    return parsed.isoformat()


def read_date_map(path: Path, conn: sqlite3.Connection) -> int:
    """Load a two-column PMID/date TSV into SQLite and return row count."""

    conn.execute("CREATE TABLE dates (pmid TEXT PRIMARY KEY, pub_date TEXT NOT NULL)")
    loaded = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                fields = next(csv.reader([line]))
            if len(fields) < 2:
                continue
            pmid = fields[0].strip()
            pub_date = normalize_date(fields[1])
            if not pmid or pmid.lower() in {"pmid", "id"}:
                continue
            if pub_date is None:
                print(
                    f"[WARNING] 日期映射第 {line_number} 行无法解析日期: {line[:120]}",
                    file=sys.stderr,
                )
                continue
            conn.execute(
                "INSERT OR REPLACE INTO dates (pmid, pub_date) VALUES (?, ?)",
                (pmid, pub_date),
            )
            loaded += 1
    conn.commit()
    return loaded


def create_database(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE articles (
            pmid TEXT PRIMARY KEY,
            file_year INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            abstract TEXT NOT NULL DEFAULT '',
            source_files TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def upsert_article(
    conn: sqlite3.Connection,
    pmid: str,
    file_year: int,
    title: str,
    abstract: str,
    source_name: str,
) -> None:
    """Merge one article, retaining the longest text seen for each passage."""

    conn.execute(
        """
        INSERT INTO articles (pmid, file_year, title, abstract, source_files)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(pmid) DO UPDATE SET
            title = CASE
                WHEN length(excluded.title) > length(articles.title)
                THEN excluded.title ELSE articles.title END,
            abstract = CASE
                WHEN length(excluded.abstract) > length(articles.abstract)
                THEN excluded.abstract ELSE articles.abstract END,
            source_files = CASE
                WHEN articles.source_files = '' THEN excluded.source_files
                WHEN instr(',' || articles.source_files || ',', ',' || excluded.source_files || ',') > 0
                    THEN articles.source_files
                ELSE articles.source_files || ',' || excluded.source_files
            END
        """,
        (pmid, file_year, title, abstract, source_name),
    )


def iter_passage_records(path: Path) -> Iterator[Tuple[str, str, str]]:
    """Yield ``(pmid, passage_type, text)`` from a PubTator file."""

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.rstrip("\r\n")
            match = PASSAGE_RE.match(line)
            if match:
                yield match.group(1).strip(), match.group(2), match.group(3).strip()


def import_pubtator_file(conn: sqlite3.Connection, path: Path, file_year: int) -> Tuple[int, int]:
    """Import title/abstract passages and return (articles_seen, passages_seen)."""

    articles_seen = 0
    passages_seen = 0
    current_pmid: Optional[str] = None
    current_title = ""
    current_abstract = ""

    def flush() -> None:
        nonlocal articles_seen, current_pmid, current_title, current_abstract
        if current_pmid is None:
            return
        upsert_article(
            conn,
            current_pmid,
            file_year,
            clean_text(current_title),
            clean_text(current_abstract),
            path.name,
        )
        articles_seen += 1
        current_pmid = None
        current_title = ""
        current_abstract = ""

    for pmid, passage_type, text in iter_passage_records(path):
        if current_pmid is not None and pmid != current_pmid:
            flush()
        if current_pmid is None:
            current_pmid = pmid
        if passage_type == "t":
            current_title = text
        else:
            current_abstract = text
        passages_seen += 1
    flush()
    conn.commit()
    return articles_seen, passages_seen


def choose_date_bounds(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str]]:
    start = normalize_date(args.start_date) if args.start_date else None
    end = normalize_date(args.end_date) if args.end_date else None
    if args.start_date and start is None:
        raise ValueError(f"无法解析 --start-date: {args.start_date}")
    if args.end_date and end is None:
        raise ValueError(f"无法解析 --end-date: {args.end_date}")
    if start and end and start > end:
        raise ValueError("--start-date 不能晚于 --end-date")
    if (start or end) and not args.date_map:
        raise ValueError("指定日期范围时必须同时提供 --date-map，因为 PubTator 文件不含出版日期")
    return start, end


def output_articles(
    conn: sqlite3.Connection,
    output_dir: Path,
    start_date: Optional[str],
    end_date: Optional[str],
    include_title: bool = False,
) -> Dict[int, Dict[str, int]]:
    """Write annual RiceMind sentence files and return per-year statistics."""

    handles: Dict[int, object] = {}
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"articles": 0, "sentences": 0})
    missing_dates = 0
    filtered_dates = 0

    try:
        query = "SELECT pmid, file_year, title, abstract, source_files FROM articles ORDER BY file_year, pmid"
        for pmid, file_year, title, abstract, _source_files in conn.execute(query):
            pub_date = None
            if start_date or end_date:
                row = conn.execute("SELECT pub_date FROM dates WHERE pmid = ?", (pmid,)).fetchone()
                pub_date = row[0] if row else None
                if pub_date is None:
                    missing_dates += 1
                    continue
                if start_date and pub_date < start_date:
                    filtered_dates += 1
                    continue
                if end_date and pub_date > end_date:
                    filtered_dates += 1
                    continue
                output_year = int(pub_date[:4])
            else:
                output_year = int(file_year)

            title_sentences = split_sentences(title) if include_title else []
            abstract_sentences = split_sentences(abstract)
            sentences = title_sentences + abstract_sentences
            if not sentences:
                continue

            if output_year not in handles:
                output_path = output_dir / f"{output_year}_filtered_sent.txt"
                handles[output_year] = output_path.open("w", encoding="utf-8", newline="\n")

            handle = handles[output_year]
            stats[output_year]["articles"] += 1
            for index, sentence in enumerate(sentences, 1):
                sentence_id = f"{pmid}_{index:04d}"
                handle.write(f"{pmid}\t{sentence_id}\t{sentence}\n")
                stats[output_year]["sentences"] += 1
    finally:
        for handle in handles.values():
            handle.close()

    if missing_dates:
        print(
            f"[WARNING] {missing_dates:,} 篇文章缺少日期映射，已跳过；"
            "如需完整月度筛选，请补全 --date-map。",
            file=sys.stderr,
        )
    if filtered_dates:
        print(f"[INFO] 按日期范围排除 {filtered_dates:,} 篇文章。")
    return stats


def build_parser() -> argparse.ArgumentParser:
    default_input_dir = PUBTATOR_DIR
    default_output_dir = SENTENCE_DIR
    parser = argparse.ArgumentParser(
        description="将 Alterome PubTator 文本转换为 RiceMind 的句子 TSV 文件"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_input_dir,
        help=f"PubTator 文件目录（默认: {default_input_dir}）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=f"RiceMind 句子输出目录（默认: {default_output_dir}）",
    )
    parser.add_argument(
        "--pattern",
        default="*.pmid-pmcid.txt",
        help="输入文件匹配模式（默认: *.pmid-pmcid.txt）",
    )
    parser.add_argument(
        "--date-map",
        type=Path,
        help="可选的 PMID 日期 TSV：PMID<TAB>YYYY-MM-DD；日期筛选时必须提供",
    )
    parser.add_argument("--start-date", help="起始日期，例如 2025-03-01")
    parser.add_argument("--end-date", help="结束日期，例如 2026-09-30")
    title_group = parser.add_mutually_exclusive_group()
    title_group.add_argument(
        "--include-title",
        dest="include_title",
        action="store_true",
        help="把文章标题也作为句子输出（默认不输出标题）",
    )
    # Keep the old option as a no-op-compatible alias.  Existing server
    # commands may still contain --exclude-title after this default changes.
    title_group.add_argument(
        "--exclude-title",
        dest="include_title",
        action="store_false",
        help="不把文章标题作为句子输出（默认行为）",
    )
    parser.set_defaults(include_title=False)
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="保留中间 SQLite 数据库，便于检查去重结果",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        start_date, end_date = choose_date_bounds(args)
    except ValueError as exc:
        parser.error(str(exc))

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not input_dir.is_dir():
        parser.error(f"输入目录不存在: {input_dir}")
    if args.date_map and not args.date_map.is_file():
        parser.error(f"日期映射文件不存在: {args.date_map}")
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(Path(path) for path in glob.glob(str(input_dir / args.pattern)))
    if not files:
        parser.error(f"输入目录中没有匹配 {args.pattern} 的文件: {input_dir}")

    fd, db_name = tempfile.mkstemp(prefix=".pubtator_to_sentence_", suffix=".sqlite3", dir=output_dir)
    os.close(fd)
    db_path = Path(db_name)

    conn = sqlite3.connect(str(db_path))
    try:
        create_database(conn)
        total_articles = 0
        total_passages = 0
        for path in files:
            try:
                year = parse_year(path)
            except ValueError as exc:
                print(f"[WARNING] {exc}，跳过文件。", file=sys.stderr)
                continue
            articles, passages = import_pubtator_file(conn, path, year)
            total_articles += articles
            total_passages += passages
            print(f"[INFO] {path.name}: articles={articles:,}, passages={passages:,}")

        unique_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        print(
            f"[INFO] 输入文章记录: {total_articles:,}；"
            f"去重后 PMID: {unique_articles:,}；标题/摘要段落: {total_passages:,}"
        )

        if args.date_map:
            loaded = read_date_map(args.date_map, conn)
            print(f"[INFO] 已加载 PMID 日期: {loaded:,}")
        elif start_date or end_date:
            # choose_date_bounds already rejects this; keep a defensive guard.
            raise RuntimeError("日期范围筛选缺少 --date-map")

        stats = output_articles(
            conn,
            output_dir,
            start_date,
            end_date,
            include_title=args.include_title,
        )
        print("[INFO] RiceMind 句子文件已生成：")
        for year in sorted(stats):
            print(
                f"  {year}_filtered_sent.txt: "
                f"articles={stats[year]['articles']:,}, "
                f"sentences={stats[year]['sentences']:,}"
            )
        if not stats:
            print("[WARNING] 没有生成句子，请检查输入内容或日期映射。", file=sys.stderr)
    finally:
        conn.close()
        if args.keep_db:
            print(f"[INFO] 中间数据库已保留: {db_path}")
        else:
            try:
                db_path.unlink()
            except FileNotFoundError:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
