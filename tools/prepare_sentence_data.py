#!/usr/bin/env python3
"""Prepare a single corpus without changing RiceMind's existing sentence filter."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_records(path, chunk_size=1024 * 1024):
    """Stream a JSON array, including non-ASCII/escaped text; reject trailing data."""
    decoder = json.JSONDecoder()
    with Path(path).open(encoding="utf-8-sig") as handle:
        buf, pos, eof = "", 0, False

        def more():
            nonlocal buf, pos, eof
            block = handle.read(chunk_size)
            buf, pos = buf[pos:] + block, 0
            if not block:
                eof = True

        def whitespace():
            nonlocal pos
            while True:
                while pos < len(buf) and buf[pos].isspace():
                    pos += 1
                if pos < len(buf) or eof:
                    return
                more()

        whitespace()
        if pos >= len(buf) or buf[pos] != "[":
            raise ValueError("Expected a JSON array: " + str(path))
        pos += 1
        whitespace()
        if pos < len(buf) and buf[pos] == "]":
            pos += 1
        else:
            while True:
                whitespace()
                while True:
                    try:
                        item, end = decoder.raw_decode(buf, pos)
                        pos = end
                        break
                    except json.JSONDecodeError as error:
                        if eof:
                            raise ValueError("Incomplete/invalid JSON: " + str(path)) from error
                        more()
                if not isinstance(item, dict):
                    raise ValueError("JSON input records must be objects")
                yield item
                whitespace()
                if pos >= len(buf):
                    raise ValueError("Unclosed JSON array")
                char = buf[pos]
                pos += 1
                if char == "]":
                    break
                if char != ",":
                    raise ValueError("Expected comma between JSON records")
                whitespace()
                if pos < len(buf) and buf[pos] == "]":
                    raise ValueError("Trailing comma in JSON array")
        whitespace()
        if pos != len(buf):
            raise ValueError("Trailing content after JSON array")


def validate_filtered(folder, years):
    folder = Path(folder)
    paths = {"combined": folder / "combined.tsv", "year_map": folder / "year_map.tsv"}
    year_by_sid = {}
    with paths["year_map"].open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not {"Sentence_ID", "Year"} <= set(reader.fieldnames or []):
            raise ValueError("Year map requires Sentence_ID and Year")
        for row in reader:
            sid, year = row["Sentence_ID"], int(row["Year"])
            if not sid or sid in year_by_sid or year not in years:
                raise ValueError("Duplicate, empty or out-of-scope year map: " + sid)
            year_by_sid[sid] = year
    records, seen = [], set()
    with paths["combined"].open(encoding="utf-8-sig") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) != 3 or not all(parts):
                raise ValueError("Invalid three-column sentence at line " + str(number))
            pmid, sid, text = parts
            if sid in seen or sid not in year_by_sid:
                raise ValueError("Duplicate sentence or missing year: " + sid)
            seen.add(sid)
            records.append((pmid, sid, text, year_by_sid[sid]))
    if seen != set(year_by_sid) or not records:
        raise ValueError("Sentence/year sets differ or corpus is empty")
    manifest_path = folder / "corpus_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name in ("combined.tsv", "year_map.tsv"):
            entry = manifest.get("files", {}).get(name)
            if entry and sha256(folder / name) != entry["sha256"]:
                raise ValueError("Corpus manifest hash mismatch: " + name)
    return records


def json_to_annual(source, destination, years):
    destination.mkdir()
    counts = {}
    seen = set()
    for year in years:
        source_file = source / (str(year) + "_filtered_sent.json")
        count = 0
        with (destination / (str(year) + "_filtered_sent.txt")).open(
                "x", encoding="utf-8", newline="\n") as out:
            for row in json_records(source_file):
                sid, text = row.get("id"), row.get("text")
                match = re.fullmatch(r"([0-9]+)_[0-9]+", sid or "")
                if not match or not isinstance(text, str) or not text or any(c in text for c in "\t\r\n"):
                    raise ValueError("Cannot reconstruct the three-column sentence: " + str(sid))
                if sid in seen:
                    raise ValueError("Duplicate sentence ID across annual inputs: " + sid)
                seen.add(sid)
                out.write(match.group(1) + "\t" + sid + "\t" + text + "\n")
                count += 1
        counts[str(year)] = count
    return counts


def prepare(args):
    years = list(range(args.start_year, args.end_year + 1))
    if not years:
        raise ValueError("Start year exceeds end year")
    selected = next((name for name in ("filtered_dir", "sentence_dir", "pubtator_dir", "oger_json_dir")
                     if getattr(args, name, None) is not None), None)
    source = Path(getattr(args, selected)).expanduser().resolve()
    if args.check_only:
        if selected != "filtered_dir":
            raise ValueError("--check-only currently validates an existing --filtered-dir")
        records = validate_filtered(source, years)
        return {"status": "checked", "sentences": len(records),
                "by_year": dict(Counter(str(r[3]) for r in records))}
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise ValueError("Output already exists; select a new directory: " + str(output))
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Input and output must be separate directory branches")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name("." + output.name + ".building-" + str(os.getpid()))
    staging.mkdir(exist_ok=False)
    report = {"status": "running", "mode": selected, "years": years, "source": str(source)}
    try:
        if selected == "filtered_dir":
            records = validate_filtered(source, years)
            for name in ("combined.tsv", "year_map.tsv", "filter_stats.json"):
                if (source / name).is_file():
                    shutil.copyfile(str(source / name), str(staging / name))
            report["filter_applied"] = False
            report["note"] = "Existing filtered IDs/text preserved; no resegmentation/refiltering."
        else:
            annual_source = source
            if selected == "pubtator_dir":
                from annotation.pubtator_to_sentence_tsv import main as convert_pubtator
                annual_source = staging / "raw_annual"
                if convert_pubtator(["--input-dir", str(source), "--output-dir", str(annual_source)]):
                    raise ValueError("PubTator preparation failed")
            elif selected == "oger_json_dir":
                annual_source = staging / "raw_annual"
                report["reconstructed_by_year"] = json_to_annual(source, annual_source, years)
            from filtration.keyword_filter_pre_oger import filter_and_merge
            temporary = staging / "filter_work"
            tsv, jfile, mapping, stats, detail = filter_and_merge(
                annual_source, temporary, years, "corpus", False)
            for src, dest in ((tsv, "combined.tsv"), (jfile, "oger.json"),
                              (mapping, "year_map.tsv"), (stats, "filter_stats.json")):
                src.rename(staging / dest)
            temporary.rmdir()
            records = validate_filtered(staging, years)
            report["filter_applied"] = True
            report["filter_counts"] = {k: v for k, v in detail.items() if k not in ("input_files", "outputs")}
        annual = staging / "annual"
        annual.mkdir()
        handles = {}
        try:
            for year in years:
                handles[year] = (annual / (str(year) + "_filtered_sent.txt")).open(
                    "x", encoding="utf-8", newline="\n")
            with (staging / "oger.json").open("w", encoding="utf-8", newline="\n") as out:
                out.write("[\n")
                first = True
                for pmid, sid, text, year in records:
                    handles[year].write(pmid + "\t" + sid + "\t" + text + "\n")
                    if not first:
                        out.write(",\n")
                    json.dump({"id": sid, "text": text}, out, ensure_ascii=False)
                    first = False
                out.write("\n]\n")
        finally:
            for handle in handles.values():
                handle.close()
        if selected != "filtered_dir":
            # Replace temporary output references with paths relative to this corpus.
            detail["outputs"] = {"combined_tsv": "combined.tsv", "oger_json": "oger.json",
                                 "sentence_year_map": "year_map.tsv"}
            detail["input_files"] = [str(source / (str(y) + "_filtered_sent.txt")) for y in years]
            if selected != "sentence_dir":
                detail["input_files"] = ["raw_annual/" + str(y) + "_filtered_sent.txt" for y in years]
            (staging / "filter_stats.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report.update(status="complete", sentences=len(records),
                      by_year=dict(Counter(str(r[3]) for r in records)),
                      outputs={p.relative_to(staging).as_posix():
                               {"bytes": p.stat().st_size, "sha256": sha256(p)}
                               for p in staging.rglob("*") if p.is_file()})
        (staging / "preparation_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if staging.resolve().parent != output.parent:
            raise ValueError("Staging directory must remain beside its intended output")
        staging.rename(output)
        return report
    except Exception as error:
        (staging / "FAILED.json").write_text(
            json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False) + "\n", encoding="utf-8")
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    for name in ("filtered-dir", "sentence-dir", "pubtator-dir", "oger-json-dir"):
        mode.add_argument("--" + name, type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--start-year", type=int, default=2025)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args(argv)
    if not args.check_only and args.output_dir is None:
        p.error("--output-dir is required unless --check-only")
    try:
        summary = prepare(args)
        print(json.dumps({k: v for k, v in summary.items() if k != "outputs"}, ensure_ascii=False))
        if not args.check_only:
            print("[OUTPUT] " + str(args.output_dir.resolve()))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("[ERROR] " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

