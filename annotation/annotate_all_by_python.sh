#!/bin/bash
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# This file is to use splited terms dictionary and get the annotations for the input. The output dir is in the script. Then for each output dir with a time stamp, this script aggregate the tsv file together.

# Batch annotation script
input_file="${RICEMIND_OGER_INPUT_JSON:-$REPO_ROOT/results/oger_input/2025_filtered_sent.json}"
termlist_dir="${RICEMIND_OGER_TERM_SPLIT_DIR:-$REPO_ROOT/OGER++/self_built_terms}"
output_base="${RICEMIND_OGER_OUTPUT_DIR:-$REPO_ROOT/results/oger}"

echo "Starting batch annotation process..."
echo "Input file: $input_file"
echo "Output base: $output_base"
echo "Termlist directory: $termlist_dir"

# Process all part files from 00 to 28
for i in {00..28}; do
    termlist_file="${termlist_dir}/self-built_terms_cleaned_part_${i}.tsv"
    output_dir="$output_base"
    
    if [ -f "$termlist_file" ]; then
        echo "=========================================="
        echo "Processing part $i: $termlist_file"
        echo "Output directory: $output_dir"
        
        # Run the annotation
        python oger_annotate_input_dic.py \
            -i "$input_file" \
            -o "$output_dir" \
            -t "$termlist_file"
        
        if [ $? -eq 0 ]; then
            echo "Successfully processed part $i"
        else
            echo "Failed to process part $i"
        fi
        
        # Wait for 2 seconds before next iteration
        echo "Waiting 2 seconds before next part..."
        sleep 2
        
    else
        echo "Termlist file not found: $termlist_file"
    fi
done

echo "=========================================="
echo "Batch annotation completed!"


# Efficient merge script
output_dir="${RICEMIND_OGER_MERGE_DIR:-$REPO_ROOT/results/oger}"
merged_file="${output_dir}/merged_all_results.tsv"

echo "Starting efficient merge..."
echo "Output directory: $output_dir"

# Create empty merged file
> "$merged_file"

# Process each timestamp directory sequentially
for timestamp_dir in "$output_dir"/2025-10-25_*/; do
    if [ -d "$timestamp_dir" ]; then
        tsv_dir="${timestamp_dir}tsv"
        if [ -d "$tsv_dir" ]; then
            dir_name=$(basename "$timestamp_dir")
            file_count=$(find "$tsv_dir" -maxdepth 1 -name "*.tsv" -type f | wc -l)
            
            if [ $file_count -gt 0 ]; then
                echo "Processing $dir_name ($file_count files)"
                cat "$tsv_dir"/*.tsv >> "$merged_file"
            fi
        fi
    fi
done

# Final statistics
total_lines=$(wc -l < "$merged_file")
echo "=========================================="
echo "Merge completed!"
echo "Total lines in merged file: $total_lines"
echo "File saved as: $merged_file"
