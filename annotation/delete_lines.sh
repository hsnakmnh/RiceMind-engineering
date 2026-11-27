#!/bin/bash
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERM_DIR="${RICEMIND_OGER_TERM_DIR:-$REPO_ROOT/OGER++}"
input_file="${RICEMIND_OGER_RAW_TERMLIST:-$TERM_DIR/self-built_terms.tsv}"
output_file="${RICEMIND_OGER_CLEANED_TERMLIST:-$TERM_DIR/self-built_terms_cleaned.tsv}"

awk -F'\t' '
NF >= 5 && 
!($4 ~ /^[-_*]+$/) && 
!($5 ~ /^[-_*]+$/) 
{print}
' "$input_file" > "$output_file"

original_lines=$(wc -l < "$input_file")
cleaned_lines=$(wc -l < "$output_file")
removed_lines=$((original_lines - cleaned_lines))

echo "Process finished!"
echo "Original number of lines: $original_lines"
echo "Deleted lines number: $removed_lines"
echo "Number of the rest lines: $cleaned_lines"
