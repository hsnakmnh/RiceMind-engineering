#!/usr/bin/env python3
"""Verify bundled resources, optionally including the separate reference bundle."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_sentence_data import validate_filtered


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_entries(root, entries):
    root = root.resolve()
    checked = 0
    for entry in entries:
        rel = Path(entry["path"])
        path = (root / rel).resolve()
        if rel.is_absolute() or ".." in rel.parts or root not in path.parents:
            raise ValueError("Manifest path must stay inside repository: " + str(rel))
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError("Missing file or size mismatch: " + str(rel))
        if digest(path) != entry["sha256"]:
            raise ValueError("SHA-256 mismatch: " + str(rel))
        checked += 1
    return checked


def check_dictionary_formats(root, entries):
    counts = {}
    for entry in entries:
        if entry["role"] not in ("oger_dictionary", "three_column_dictionary"):
            continue
        path = root / entry["path"]
        expected = 6 if entry["role"] == "oger_dictionary" else 3
        count = 0
        with path.open(encoding="utf-8-sig") as f:
            for number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                if len(line.rstrip("\r\n").split("\t")) != expected:
                    raise ValueError("{}:{} expected {} columns".format(path.name, number, expected))
                count += 1
        if count == 0:
            raise ValueError("Empty dictionary: " + str(path))
        counts[path.name] = count
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-references", action="store_true",
                        help="Also require and hash-check the separate reference bundle")
    parser.add_argument("--models", action="store_true",
                        help="Also check OGER import and the configured SciSpacy config.cfg; no inference")
    parser.add_argument("--require-corpus", action="store_true",
                        help="Fail if the optional literature-text snapshot is not installed")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads((ROOT / "resources/manifest.json").read_text(encoding="utf-8"))
        checked = check_entries(ROOT, manifest["entries"])
        counts = check_dictionary_formats(ROOT, manifest["entries"])
        print("[OK] Bundled resource hashes:", checked)
        print("[OK] Dictionary rows:", json.dumps(counts, sort_keys=True))
        corpus = ROOT / "datasets/2025-2026-keyword-filtered"
        if args.require_corpus or (corpus / "combined.tsv").exists() or (corpus / "year_map.tsv").exists():
            rows = validate_filtered(corpus, [2025, 2026])
            print("[OK] Filtered corpus:", len(rows))
        else:
            print("[NOTE] Optional literature-text snapshot not installed; use your own corpus or a permitted data bundle")
        if args.with_references:
            manifest = json.loads((ROOT / "resources/reference_bundle_manifest.json").read_text(encoding="utf-8"))
            checked = check_entries(ROOT, manifest["entries"])
            print("[OK] Reference bundle hashes:", checked)
        if args.models:
            import oger
            from ricemind_config import SCISPACY_MODEL
            if not (SCISPACY_MODEL / "config.cfg").is_file():
                raise ValueError("SciSpacy model config.cfg missing: " + str(SCISPACY_MODEL))
            print("[OK] OGER imported; SciSpacy model config present (load/inference not tested)")
        return 0
    except (OSError, ValueError, KeyError, ImportError) as error:
        print("[ERROR]", error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

