#!/usr/bin/env python3
"""Export row-level coverage sets using compare_gta_coverage.py's exact rules.

This reporting helper does not alter annotation, mapping, filtering, or set
comparison methods. It exports unique RAP_ID and (RAP_ID, Ontology_ID) sets,
then attaches the existing trend fields and sentence-level evidence to NLP-only
GTA pairs.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path, required):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("Missing or empty input: {}".format(path))
    frame = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError("{} lacks required columns: {}".format(path, ", ".join(sorted(missing))))
    return path, frame


def write_set(path, values, columns):
    frame = pd.DataFrame(sorted(values), columns=columns)
    frame.to_csv(path, sep="\t", index=False)
    return len(frame)


def ontology_group(value):
    if value.startswith("GO:"):
        return "GO"
    if value.startswith("PO:"):
        return "PO"
    if value.startswith(("TO:", "RTO:", "CO_")):
        return "TO_GROUP"
    return "OTHER"


def actual_prefix(value):
    if value.startswith(("TO:", "RTO:", "CO_")):
        return value.split(":", 1)[0] + ":" if ":" in value else "CO_"
    match = re.match(r"^([A-Za-z][A-Za-z0-9]*[:_])", value)
    return match.group(1) if match else "(no prefix)"


def unique_join(values):
    return ";".join(sorted({value for value in values if value}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-file", required=True, type=Path)
    parser.add_argument("--association-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path,
                        help="Defaults to <association-dir>/coverage_details; existing directories are rejected.")
    args = parser.parse_args()

    association_dir = args.association_dir.expanduser().resolve()
    public_path, public = read_table(args.public_file, ("RAP_ID", "Ontology_ID"))
    trend_path, trend = read_table(association_dir / "NLP_Rice_GTA_Trend.tsv",
                                   ("RAP_ID", "Ontology_ID"))
    sentence_path, sentence = read_table(association_dir / "NLP_Rice_GTA_Database.tsv",
                                         ("RAP_ID", "Ontology_ID", "PMID", "Sentence_ID", "Sentence_Text"))

    # Keep the author's original predicate and exact set keys unchanged.
    valid_public = public[public["RAP_ID"].str.startswith("Os")]
    valid_trend = trend[trend["RAP_ID"].str.startswith("Os")]
    valid_sentences = sentence[sentence["RAP_ID"].str.startswith("Os")]
    public_genes = set(valid_public["RAP_ID"])
    nlp_genes = set(valid_trend["RAP_ID"])
    public_pairs = set(zip(valid_public["RAP_ID"], valid_public["Ontology_ID"]))
    nlp_pairs = set(zip(valid_trend["RAP_ID"], valid_trend["Ontology_ID"]))
    shared_genes, nlp_only_genes = public_genes & nlp_genes, nlp_genes - public_genes
    shared_pairs, nlp_only_pairs = public_pairs & nlp_pairs, nlp_pairs - public_pairs
    public_only_pairs = public_pairs - nlp_pairs

    output = (args.output_dir or association_dir / "coverage_details").expanduser().resolve()
    if output.exists():
        parser.error("Output directory already exists; choose a new path: {}".format(output))
    output.mkdir(parents=True)

    counts = {}
    counts["gene_ids_shared"] = write_set(output / "gene_ids_shared.tsv", shared_genes, ["RAP_ID"])
    counts["gene_ids_nlp_only"] = write_set(output / "gene_ids_nlp_only.tsv", nlp_only_genes, ["RAP_ID"])
    counts["gene_ids_public_only"] = write_set(output / "gene_ids_public_only.tsv", public_genes - nlp_genes, ["RAP_ID"])
    counts["gta_pairs_shared"] = write_set(output / "gta_pairs_shared.tsv", shared_pairs,
                                           ["RAP_ID", "Ontology_ID"])
    counts["gta_pairs_public_only"] = write_set(output / "gta_pairs_public_only.tsv", public_only_pairs,
                                                ["RAP_ID", "Ontology_ID"])

    trend_only = valid_trend[
        valid_trend.apply(lambda row: (row["RAP_ID"], row["Ontology_ID"]) in nlp_only_pairs, axis=1)
    ]
    detail_rows = []
    for (rap_id, ontology_id), group in trend_only.groupby(["RAP_ID", "Ontology_ID"], sort=True):
        row = {"RAP_ID": rap_id, "Ontology_ID": ontology_id}
        for column in ("Gene_Symbol", "Ontology_Type", "Trait_Description", "Evidence_Code",
                       "Source_DB", "Reference", "Article_Count", "First_Mention_Year",
                       "Original_Gene_ID", "Gene_Key", "Mapping_Status", "Candidate_Gene_Keys",
                       "Trait_Name_Candidates", "Sentence_Count"):
            if column in group.columns:
                row[column] = (unique_join(group[column]) if column in
                               ("Gene_Symbol", "Ontology_Type", "Trait_Description", "Reference",
                                "Original_Gene_ID", "Gene_Key", "Mapping_Status", "Candidate_Gene_Keys",
                                "Trait_Name_Candidates") else unique_join(group[column]))
        detail_rows.append(row)
    detail_columns = ["RAP_ID", "Ontology_ID"] + [c for c in (
        "Gene_Symbol", "Ontology_Type", "Trait_Description", "Evidence_Code", "Source_DB",
        "Reference", "Article_Count", "First_Mention_Year", "Original_Gene_ID", "Gene_Key",
        "Mapping_Status", "Candidate_Gene_Keys", "Trait_Name_Candidates", "Sentence_Count")
        if c in valid_trend.columns]
    pd.DataFrame(detail_rows, columns=detail_columns).to_csv(
        output / "gta_pairs_nlp_only.tsv", sep="\t", index=False)
    counts["gta_pairs_nlp_only"] = len(detail_rows)

    sentence_keys = list(zip(valid_sentences["RAP_ID"], valid_sentences["Ontology_ID"]))
    evidence = valid_sentences.loc[[key in nlp_only_pairs for key in sentence_keys]].copy()
    evidence.to_csv(output / "gta_pairs_nlp_only_sentence_evidence.tsv", sep="\t", index=False)
    counts["nlp_only_sentence_evidence_rows"] = len(evidence)

    prefix_counts = {}
    for label, pair_set in (("all_nlp_os_pairs", nlp_pairs), ("nlp_only_pairs", nlp_only_pairs)):
        grouped = {}
        for _, ontology_id in pair_set:
            prefix = actual_prefix(ontology_id)
            bucket = ontology_group(ontology_id)
            key = (bucket, prefix)
            grouped[key] = grouped.get(key, 0) + 1
        rows = [{"Comparison_Set": label, "Group": group, "Ontology_Prefix": prefix, "Unique_Pairs": count}
                for (group, prefix), count in sorted(grouped.items())]
        prefix_counts[label] = sum(row["Unique_Pairs"] for row in rows if row["Group"] == "OTHER")
        if label == "all_nlp_os_pairs":
            prefix_rows = rows
        else:
            prefix_rows.extend(rows)
    pd.DataFrame(prefix_rows, columns=["Comparison_Set", "Group", "Ontology_Prefix", "Unique_Pairs"]).to_csv(
        output / "ontology_prefix_summary.tsv", sep="\t", index=False)

    summary = {
        "status": "complete",
        "method": {
            "gene_filter": "RAP_ID startswith Os",
            "gene_key": "unique RAP_ID",
            "gta_key": "unique exact (RAP_ID, Ontology_ID)",
            "ontology_groups": {"GO": ["GO:"], "PO": ["PO:"], "TO_GROUP": ["TO:", "RTO:", "CO_"]},
        },
        "counts": {
            "public_unique_genes": len(public_genes), "nlp_unique_genes": len(nlp_genes),
            "shared_genes": len(shared_genes), "nlp_only_genes": len(nlp_only_genes),
            "public_unique_gta_pairs": len(public_pairs), "nlp_unique_gta_pairs": len(nlp_pairs),
            "shared_gta_pairs": len(shared_pairs), "nlp_only_gta_pairs": len(nlp_only_pairs),
            "public_only_gta_pairs": len(public_only_pairs),
            "nlp_other_prefix_pairs": prefix_counts["all_nlp_os_pairs"],
            "nlp_only_other_prefix_pairs": prefix_counts["nlp_only_pairs"],
            **counts,
        },
        "inputs": {str(path): {"bytes": path.stat().st_size, "sha256": file_hash(path)}
                   for path in (public_path, trend_path, sentence_path)},
        "created_at": datetime.now().astimezone().isoformat(),
        "note": "NLP-only means absent from this public snapshot under the stated exact-set rules; it does not establish biological novelty.",
    }
    (output / "coverage_details_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[SUMMARY] " + json.dumps(summary["counts"], ensure_ascii=False), flush=True)
    print("[OUTPUT] " + str(output), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
