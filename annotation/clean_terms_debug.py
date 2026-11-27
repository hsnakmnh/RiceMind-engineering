#!/usr/bin/env python3
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from ricemind_config import OGER_TERMLIST

_term_dir = Path(os.environ.get("RICEMIND_OGER_TERM_DIR", str(OGER_TERMLIST.parent)))
input_file = os.environ.get("RICEMIND_OGER_RAW_TERMLIST", str(_term_dir / "self-built_terms.tsv"))
output_file = os.environ.get(
    "RICEMIND_OGER_CLEANED_TERMLIST",
    str(_term_dir / "self-built_terms_cleaned_python.tsv"),
)

print("=== Start processing ===")

# Read original file
with open(input_file, 'r', encoding='utf-8') as f:
    original_lines = [line.strip() for line in f if line.strip()]

print(f"Original valid lines: {len(original_lines)}")

# Process file
meaningless_pattern = re.compile(r'^[-_*]+$')
cleaned_count = 0
valid_lines = []

for line in original_lines:
    columns = line.split('\t')
    
    if len(columns) >= 5:
        col4 = columns[3].strip() if len(columns) > 3 else ""
        col5 = columns[4].strip() if len(columns) > 4 else ""
        
        if meaningless_pattern.match(col4) or meaningless_pattern.match(col5):
            cleaned_count += 1
            continue
    
    valid_lines.append(line)

# Write output file
with open(output_file, 'w', encoding='utf-8') as f:
    for line in valid_lines:
        f.write(line + '\n')

print("=== Results ===")
print(f"Process finished!")
print(f"Original number of lines: {len(original_lines)}")
print(f"Deleted lines number: {cleaned_count}")
print(f"Number of the rest lines: {len(valid_lines)}")

# Verification
print("=== Verification ===")
with open(output_file, 'r', encoding='utf-8') as f:
    output_lines = [line.strip() for line in f if line.strip()]
print(f"Output file actual lines: {len(output_lines)}")
