# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import pandas as pd
import csv
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import GTA_DATA_DIR, STANDARD_GENE_DIR

# ==========================================
# 配置路径（统一由 ricemind_config.py 管理）
# ==========================================
base_dir = str(GTA_DATA_DIR.parent)
oryzabase_file = os.path.join(str(STANDARD_GENE_DIR), "OryzabaseGeneListEn_20250702010110.txt")
nlp_gta_file = os.path.join(str(GTA_DATA_DIR), "NLP_Rice_GTA_Database.tsv")
output_nlp_gta_file = os.path.join(str(GTA_DATA_DIR), "Mapped_NLP_Rice_GTA_Database.tsv")

def map_nlp_to_rap():
    # 1. 读取 Oryzabase，构建 Trait Gene Id -> RAP ID 的字典
    print(f"Reading Oryzabase from {oryzabase_file}...")
    df_oryza = pd.read_csv(oryzabase_file, sep='\t', dtype=str)
    
    oryza_to_rap_map = {}
    for _, row in df_oryza.iterrows():
        trait_id = str(row['Trait Gene Id']).strip()
        rap_id = str(row['RAP ID']).strip()
        
        # 仅保留拥有 RAP ID 的条目
        if rap_id and rap_id != 'nan':
            # 如果存在多个逗号分隔的 RAP ID，默认取第一个
            clean_rap_id = rap_id.split(',')[0].strip()
            oryza_to_rap_map[trait_id] = clean_rap_id
            
    print(f"Built mapping dictionary with {len(oryza_to_rap_map)} entries.")

    # 2. 读取之前生成的 NLP GTA 文件
    print(f"Reading NLP GTA database from {nlp_gta_file}...")
    df_nlp = pd.read_csv(nlp_gta_file, sep='\t', dtype=str)
    
    # 确保存储列处理时不出现 nan 字符串
    df_nlp = df_nlp.fillna("")
    
    mapped_count = 0
    unmapped_count = 0

    # 3. 映射逻辑函数
    def get_rap_id(orig_id):
        nonlocal mapped_count, unmapped_count
        orig_id_str = str(orig_id).strip()
        
        if orig_id_str.startswith("OryzaGeneID:"):
            # 提取冒号后面的纯数字 ID
            num_id = orig_id_str.split(":")[-1]
            if num_id in oryza_to_rap_map:
                mapped_count += 1
                return oryza_to_rap_map[num_id]
                
        unmapped_count += 1
        return "" # 如果在 Oryzabase 里找不到对应的 RAP ID，则保持为空

    # 4. 应用映射并更新 RAP_ID 列
    print("Mapping OryzaGeneID to standard RAP_ID...")
    df_nlp['RAP_ID'] = df_nlp['Original_ID'].apply(get_rap_id)

    # 5. 保存结果
    df_nlp.to_csv(output_nlp_gta_file, sep='\t', index=False, quoting=csv.QUOTE_NONE, escapechar='\\')
    
    print("\n--- Summary ---")
    print(f"Successfully mapped: {mapped_count} records.")
    print(f"Unmapped records (No RAP ID in Oryzabase): {unmapped_count}")
    print(f"Saved mapped NLP GTA to: {output_nlp_gta_file}")

if __name__ == "__main__":
    map_nlp_to_rap()
