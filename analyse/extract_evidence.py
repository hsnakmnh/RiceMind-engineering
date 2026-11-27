# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import json
import re
import sys
import argparse
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
import sys

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import KEYWORD_OUTPUT, SUPP_DICT_DIR

def clean_entity(name):
    if not isinstance(name, str):
        return ""
    return name.replace('[', '').replace(']', '').replace('*', '').strip().upper()

def extract_ontology_ids(text):
    if not isinstance(text, str):
        return []
    return re.findall(r'\b(GO:\d+|TO:\d+|RTO:\d+)\b', text)

def load_dictionaries(dict_dir):
    term_map = {}
    dict_files = ['go_oger_dict.tsv', 'to_oger_dict.tsv', 'rto_oger_dict.tsv']
    
    for d_file in dict_files:
        path = os.path.join(dict_dir, d_file)
        if not os.path.exists(path):
            continue
            
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip('\n').split('\t')
                if len(parts) >= 5:
                    term_id = parts[2]
                    term_name = parts[4]
                    term_map[term_id] = term_name
                    
    return term_map

def main():
    parser = argparse.ArgumentParser(description="Extract sentence evidence for a Gene-Trait pair")
    parser.add_argument("--gene", required=True, help="Standard Gene Symbol")
    parser.add_argument("--trait", required=True, help="Trait ID (e.g., GO:0043036)")
    parser.add_argument("--file", default=str(KEYWORD_OUTPUT), help="Path to jsonl")
    parser.add_argument("--dict_dir", default=str(SUPP_DICT_DIR), help="Path to dictionary directory")
    parser.add_argument("--limit", type=int, default=5, help="Max sentences to display")
    args = parser.parse_args()

    term_map = load_dictionaries(args.dict_dir)
    trait_name = term_map.get(args.trait, "Name Not Found In Dictionary")

    print("=" * 70)
    print(f"Searching evidence for:")
    print(f"Gene:  {args.gene}")
    print(f"Trait: {args.trait} ({trait_name})")
    print("=" * 70)
    
    total_lines = 0
    if os.path.exists(args.file):
        with open(args.file, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)
    else:
        print(f"Error: File {args.file} not found.")
        return

    found = 0
    with open(args.file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i % 2000 == 0:
                pct = (i / total_lines) * 100
                sys.stdout.write(f"\rProgress: [{i}/{total_lines}] {pct:.2f}%")
                sys.stdout.flush()

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            has_gene = False
            has_trait = False

            annotations = data.get('annotations', {})
            for tool_name, entities in annotations.items():
                for ent in entities:
                    cat = ent.get('cat')
                    if cat == 'Gene':
                        norm = ent.get('Normalization', '')
                        if clean_entity(norm) == clean_entity(args.gene):
                            has_gene = True
                    elif cat in ['Phenotype', 'Trait']:
                        trait_id = ent.get('id', '')
                        found_ids = extract_ontology_ids(trait_id)
                        if args.trait in found_ids:
                            has_trait = True

            if has_gene and has_trait:
                pct = (i / total_lines) * 100
                sys.stdout.write(f"\rProgress: [{i}/{total_lines}] {pct:.2f}% - FOUND MATCH!\n")
                print(f"\n[Evidence {found + 1}] Year: {data.get('year')} | PMID: {data.get('PMID')}")
                print(f"Journal: {data.get('journal')}")
                print(f"Sentence: {data.get('text')}\n")
                print("-" * 70)
                
                found += 1
                if found >= args.limit:
                    break

    print(f"\nSearch complete. Displayed {found} examples.")

if __name__ == "__main__":
    main()
