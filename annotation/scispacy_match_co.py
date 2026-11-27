# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import spacy
import os
import csv
import sys
from tqdm import tqdm

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import DICT_PATHS, SCISPACY_MODEL, SCISPACY_OUTPUT_ROOT, SENTENCE_DIR

# --- Configuration & Paths ---
# Path to the local SciSpacy model (SciBERT).  The old server path is kept as
# a fallback for compatibility; use an environment variable on a new server.
MODEL_PATH = str(SCISPACY_MODEL)

# Path to the co-trait dictionary.
DICT_PATH = str(DICT_PATHS["co"])

# Directory containing all year files (1985-2025)
DATA_DIR = str(SENTENCE_DIR)

# Output directory
OUTPUT_DIR = os.path.join(str(SCISPACY_OUTPUT_ROOT), "scispacy_co_result")

def main():
    # 1. Setup Output Directory
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"[INFO] Created output directory: {OUTPUT_DIR}")
        except OSError as e:
            print(f"[ERROR] Could not create directory {OUTPUT_DIR}: {e}")
            sys.exit(1)

    # 2. Load Model
    print(f"[INFO] Loading SciSpacy model from: {MODEL_PATH}")
    config_path = os.path.join(MODEL_PATH, "config.cfg")
    if not os.path.exists(config_path):
        print(f"[ERROR] config.cfg not found at {config_path}")
        sys.exit(1)

    try:
        # Disable heavy components to maximize speed for large scale processing
        nlp = spacy.load(MODEL_PATH, disable=["ner", "parser", "tagger", "lemmatizer", "transformer", "attribute_ruler"])
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        sys.exit(1)

    # 3. Build EntityRuler and Name Lookup
    print("[INFO] Building dictionary patterns...")
    # validate=True checks if patterns contain tokens not in the vocab, safe to keep
    ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER", "validate": True})

    patterns = []
    id_to_std_name = {}

    try:
        with open(DICT_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if len(row) < 2: continue
                
                rto_id = row[0]
                std_name = row[1]
                synonyms_str = row[2] if len(row) > 2 else ""
                
                # Map ID to Standard Name
                id_to_std_name[rto_id] = std_name

                # Collect patterns
                names = set()
                names.add(std_name)
                if synonyms_str and synonyms_str.strip():
                    for syn in synonyms_str.split('|'):
                        if syn.strip():
                            names.add(syn.strip())
                
                for name in names:
                    patterns.append({"label": rto_id, "pattern": name})
        
        ruler.add_patterns(patterns)
        print(f"[INFO] Loaded {len(patterns)} patterns from dictionary.")
        
    except FileNotFoundError:
        print(f"[ERROR] Dictionary file not found at {DICT_PATH}")
        sys.exit(1)

    # 4. Get List of Files
    all_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.txt')]
    all_files.sort() # Process in chronological order
    
    print(f"[INFO] Found {len(all_files)} files to process in {DATA_DIR}")

    # 5. Process Files Loop
    # Using tqdm for a progress bar across files
    for filename in tqdm(all_files, desc="Overall Progress", unit="file"):
        
        file_path = os.path.join(DATA_DIR, filename)
        output_filename = filename.replace(".txt", "_result.tsv")
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        # Skip if output already exists (optional, currently overwrites)
        # if os.path.exists(output_path): continue 

        sentences_data = []
        
        # Read sentences
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 3:
                        # parts[0]=PMID, parts[1]=SentID, parts[2]=Text
                        sentences_data.append((parts[0], parts[1], parts[2]))
        except Exception as e:
            print(f"\n[ERROR] Could not read file {filename}: {e}")
            continue

        if not sentences_data:
            continue

        # Write results for this file
        with open(output_path, 'w', encoding='utf-8', newline='') as out_f:
            writer = csv.writer(out_f, delimiter='\t')
            
            # --- [UPDATED] Header with 8 columns ---
            writer.writerow([
                "PMID", 
                "Sentence_ID", 
                "Trait_ID",      # Changed from CO_ID to Trait_ID
                "Standard_Name", 
                "Start",         # New Column
                "End",           # New Column
                "Matched_Text", 
                "Sentence_Text"
            ])
            
            texts = [item[2] for item in sentences_data]
            
            # Batch processing with nlp.pipe
            docs = nlp.pipe(texts, batch_size=2000)
            
            match_count = 0
            
            # Use zip to iterate through original data and processed docs
            for (pmid, sent_id, raw_text), doc in zip(sentences_data, docs):
                if len(doc.ents) > 0:
                    for ent in doc.ents:
                        # FILTER: Skip short matches (< 3 characters)
                        if len(ent.text) < 3:
                            continue

                        std_name = id_to_std_name.get(ent.label_, "Unknown")

                        # --- [UPDATED] Row writing logic ---
                        # ent.start_char: The character offset for the start of the entity in the doc.
                        # ent.end_char: The character offset for the end of the entity in the doc.
                        writer.writerow([
                            pmid,
                            sent_id,
                            ent.label_,        # Trait_ID
                            std_name,          # Standard_Name
                            ent.start_char,    # Start
                            ent.end_char,      # End
                            ent.text,          # Matched_Text
                            raw_text           # Sentence_Text
                        ])
                        match_count += 1
        
        # Optional: Print summary for this file
        # print(f"File: {filename} | Matches: {match_count}")

    print("\n--------------------------------------------------")
    print("[INFO] All files processed successfully.")
    print(f"[INFO] Results are saved in: {OUTPUT_DIR}")
    print("--------------------------------------------------")

if __name__ == "__main__":
    main()
