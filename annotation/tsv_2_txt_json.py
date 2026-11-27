# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
# This script can transfer the current sent tsv file to a accessible file (txt_json) for OGER.

import json
import os
import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from ricemind_config import OGER_INPUT_DIR, SENTENCE_DIR

def convert_tsv_to_txtjson(input_file, output_file):
    """
    Convert tab-separated text file to txt.json format
    
    Args:
        input_file: input file path
        output_file: output file path
    """
    result = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:  # skip empty lines
                continue
                
            # Split by tab
            parts = line.split('\t')
            
            if len(parts) < 3:
                print(f"Warning: Line {line_num} has insufficient fields, skipping: {line}")
                continue
            
            # Second column is ID, third column is text
            doc_id = parts[1]
            text = parts[2]
            
            # Create JSON object
            doc_obj = {
                "id": doc_id,
                "text": text
            }
            
            result.append(doc_obj)
    
    # Save as JSON file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    return len(result)

def batch_process_files(input_dir, output_dir, start_year=2025, end_year=2026):
    """
    Batch process files from start_year to end_year
    
    Args:
        input_dir: input directory path
        output_dir: output directory path
        start_year: start year
        end_year: end year
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    total_records = 0
    processed_files = 0
    skipped_files = 0
    
    for year in range(start_year, end_year + 1):
        input_file = os.path.join(input_dir, f"{year}_filtered_sent.txt")
        output_file = os.path.join(output_dir, f"{year}_filtered_sent.json")
        
        if os.path.exists(input_file):
            try:
                print(f"Processing: {input_file}")
                records_count = convert_tsv_to_txtjson(input_file, output_file)
                total_records += records_count
                processed_files += 1
                print(f"  Generated: {output_file} ({records_count} records)")
            except Exception as e:
                print(f"  Error processing: {e}")
                skipped_files += 1
        else:
            print(f"Warning: File not found, skipping: {input_file}")
            skipped_files += 1
    
    print(f"\nBatch processing completed!")
    print(f"Files processed: {processed_files}")
    print(f"Files skipped: {skipped_files}")
    print(f"Total records: {total_records}")

def main():
    parser = argparse.ArgumentParser(description='Convert TSV format to txt.json format')
    parser.add_argument('--mode', choices=['single', 'batch'], default='batch',
                       help='Processing mode: single file or batch (default: batch)')
    parser.add_argument('--input', help='Input file path or directory')
    parser.add_argument('--output', help='Output file path or directory')
    parser.add_argument('--start-year', type=int, default=2025,
                       help='Start year for batch processing (default: 2025)')
    parser.add_argument('--end-year', type=int, default=2026,
                       help='End year for batch processing (default: 2026)')
    
    args = parser.parse_args()
    
    if args.mode == 'single':
        if not args.input or not args.output:
            print("Error: For single mode, both --input and --output are required")
            return
        
        convert_tsv_to_txtjson(args.input, args.output)
    else:
        # Use the default paths you provided
        input_dir = str(SENTENCE_DIR)
        output_dir = str(OGER_INPUT_DIR)
        
        # Use command line arguments if provided
        if args.input:
            input_dir = args.input
        if args.output:
            output_dir = args.output
        
        print(f"Input directory: {input_dir}")
        print(f"Output directory: {output_dir}")
        print(f"Processing years: {args.start_year} - {args.end_year}")
        print("-" * 50)
        
        batch_process_files(input_dir, output_dir, args.start_year, args.end_year)

if __name__ == "__main__":
    main()
