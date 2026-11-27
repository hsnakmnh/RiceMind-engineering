# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import pandas as pd
import json
import csv
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import GTA_DATA_DIR, KEYWORD_OUTPUT

# ==========================================
# 配置路径（统一由 ricemind_config.py 管理）
# ==========================================
base_dir = str(GTA_DATA_DIR.parent)
jsonl_file = str(KEYWORD_OUTPUT)
mapped_tsv = os.path.join(str(GTA_DATA_DIR), "Mapped_NLP_Rice_GTA_Database.tsv")
output_tsv = os.path.join(str(GTA_DATA_DIR), "Trend_NLP_Rice_GTA_Database.tsv")

def aggregate_gta_trends():
    print(f"Step 1: Scanning JSONL to extract publication years from {jsonl_file}...")
    trend_records = []
    
    # 解析 JSONL，收集每次提及的年份和 PMID
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            
            data = json.loads(line)
            pmid = data.get("PMID", "")
            year_str = data.get("year", "")
            
            if not pmid or not year_str: continue
            
            try:
                year = int(year_str)
            except ValueError:
                continue
                
            annotations = data.get("annotations", {})
            genes = set()
            traits = set()
            
            # 提取该句子中的所有实体 ID
            for tool, entities in annotations.items():
                for ent in entities:
                    cat = ent.get("cat")
                    ent_id = str(ent.get("id"))
                    if cat == "Gene":
                        genes.add(ent_id)
                    elif cat == "Phenotype":
                        traits.add(ent_id)
                        
            # 构建该句子中的 GTA 组合
            if genes and traits:
                for g in genes:
                    for t in traits:
                        trend_records.append({
                            'Original_ID': g,
                            'Ontology_ID': t,
                            'PMID': pmid,
                            'Year': year
                        })
                        
    df_trends = pd.DataFrame(trend_records)
    print(f"Extracted {len(df_trends)} raw mention records from JSONL.")

    print("Step 2: Aggregating trends (Calculating Article Count and First Year)...")
    # 按照 Gene 和 Trait 分组聚合
    agg_df = df_trends.groupby(['Original_ID', 'Ontology_ID']).agg(
        Article_Count=('PMID', 'nunique'),     # 统计有多少个不同的文献
        First_Mention_Year=('Year', 'min'),    # 找出最早的年份
        All_PMIDs=('PMID', lambda x: ';'.join(set(x))) # 将支持的 PMID 拼接到一起备查
    ).reset_index()

    print(f"Step 3: Loading Mapped TSV to merge information: {mapped_tsv}")
    df_mapped = pd.read_csv(mapped_tsv, sep='\t', dtype=str).fillna("")
    
    # 因为我们要把 178 万行压缩为 Unique GTA，所以先对原表去重
    # 丢弃原表中单独的 Reference 列，因为我们会在后面换成 aggregated 的 All_PMIDs 和 Count
    df_unique_gta = df_mapped.drop_duplicates(subset=['Original_ID', 'Ontology_ID']).copy()
    if 'Reference' in df_unique_gta.columns:
        df_unique_gta = df_unique_gta.drop(columns=['Reference'])

    print("Step 4: Merging trend data into the Unique GTA database...")
    # 将聚合后的统计数据左连接合并回主表
    final_df = pd.merge(df_unique_gta, agg_df, on=['Original_ID', 'Ontology_ID'], how='left')
    
    # 填充那些可能在 JSONL 解析中遗漏的空值
    final_df['Article_Count'] = final_df['Article_Count'].fillna(1).astype(int)
    final_df['First_Mention_Year'] = final_df['First_Mention_Year'].fillna(0).astype(int)

    # 保存
    final_df.to_csv(output_tsv, sep='\t', index=False, quoting=csv.QUOTE_NONE, escapechar='\\')
    
    print("\n--- Summary ---")
    print(f"Original TSV rows (Mentions): {len(df_mapped)}")
    print(f"Compressed Unique GTAs:       {len(final_df)}")
    print(f"Saved final trend database to: {output_tsv}")

if __name__ == "__main__":
    aggregate_gta_trends()
