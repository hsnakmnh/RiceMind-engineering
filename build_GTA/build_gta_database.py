# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
'''
=========================================================================================
Script Name: build_gta_database.py
Description: 多源公共数据库的水稻基因-表型关联（GTA）统一化与整合流水线
Author: [您的名字/实验室]
Date: [当前日期]

【脚本功能概述 (Abstract)】
本脚本是 RiceMind 知识图谱公共数据基座的构建核心。由于不同的公共生物信息学数据库（如 Oryzabase, 
RAP-DB, Ensembl, Planteome）在数据格式、本体（Ontology）标准以及基因标识符（Identifiers）上存在
显著的异构性，本脚本旨在执行深度的数据清洗、实体对齐（Entity Alignment）与跨域映射（Cross-domain 
Mapping）。最终，将散落的多源证据聚合为一个高度标准化、去重且以 RAP ID 为全局唯一主键的统一知识库
（Unified Rice GTA Database），为后续与 NLP 挖掘结果进行交叉验证提供金标准（Gold Standard）。

【数据源解析与处理模块 (Materials & Methods)】

1. Oryzabase (专家人工精审库)
   - 作用：提供最高置信度（Curated）的表型、解剖与功能关联，同时作为基因命名的官方基准。
   - 处理逻辑：提取并格式化 CGSNL 官方命名及同义词网络（转化为 `"sym1";"sym2"` 格式）；基于正则
     表达式精准解析混杂在文本中的 GO/TO/PO 本体 ID；同时，动态构建 `Gramene ID -> RAP ID` 的映射字典
     供下游模块使用。

2. RAP-DB (参考基因组注释库)
   - 作用：提供基于 IRGSP-1.0 参考基因组的高质量 Gene Ontology (GO) 注释。
   - 处理逻辑：解析嵌有文献 PMID 与本体描述的复合字符串，将基因组位点级别的数据标准化为通用 GTA 格式。

3. Ensembl Plants (大规模全基因组注释库)
   - 作用：补充大规模的结构与功能注释。
   - 处理逻辑：执行严格的标识符过滤，仅保留拥有标准水稻 `Os` 前缀主键的高效记录。

4. Planteome 与跨层级 ID 映射 (Cross-level ID Mapping) - [论文核心方法]
   - 挑战：Planteome 提供了极具价值的跨物种表型与解剖学本体（TO/PO），但其原始 `assoc` 文件中，
     大量的关联是建立在**蛋白质层级（Protein ID）**或外部参照（如 Gramene ID）之上的。
   - 解决策略（双重保险映射机制）：
     a) 导入外部的 `protein_gene_mapping.txt` 构建 `Protein -> RAP ID` 字典。
     b) 导入 Oryzabase 模块生成的 `Gramene -> RAP ID` 字典。
     c) 在遍历 Planteome 记录时，通过多级回溯（先查直接 ID，再查 Gramene 字典，最后解析 `With/From` 
        字段查 Protein 字典），将蛋白质-表型关联（Protein-Trait Associations）成功“降维”并对齐到
        统一的基因-表型关联（Gene-Trait Associations, GTAs）底座上。

【数据整合与后处理 (Data Integration & Post-processing)】
1. 纵向拼接 (Concatenation)：将四个独立清洗后的 DataFrame 无缝合并。
2. 知识级去重 (Deduplication)：以 `['RAP_ID', 'Ontology_ID', 'Evidence_Code']` 为联合主键进行
   严格去重。这确保了如果多个数据库通过相同的证据类型支持了同一对关联，在金标准库中只保留一条最
   干净的记录，从而防止下游统计时的权重偏移。
3. 容错导出：处理缺失值，禁用自动转义以防制表符错位，输出为标准 TSV 格式。

【输出产物 (Output)】
- `Unified_Rice_GTA_Database.tsv`：整合后的金标准结构化关联表。
=========================================================================================

(Alterome_RDF) [ywliu@localhost gta]$ python build_gta_database.py
Processing Oryzabase from the path in ricemind_config.py...
Extracted 117796 rows from Oryzabase.
Built Gramene -> RAP ID map with 392 entries.
Processing RAP-DB from the path in ricemind_config.py...
Extracted 54421 rows from RAP-DB.
Processing Ensembl from the path in ricemind_config.py...
Extracted 64779 rows from Ensembl.
Loading protein mapping dictionary from the path in ricemind_config.py...
Built Protein -> RAP ID map with 185872 entries.
Processing Planteome from the path in ricemind_config.py...
Extracted 121805 rows from Planteome.
Merging all databases...
Successfully built Unified GTA Database! Total unique records: 346282
Saved to the path in ricemind_config.py.

'''


import pandas as pd
import re
import os
import warnings
import csv
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import GTA_DIR, GTA_OTHER_DB_DIR, STANDARD_GENE_DIR

# 忽略 pandas 的某些警告以保持控制台整洁
warnings.filterwarnings('ignore')

# ==========================================
# 1. 通用辅助函数
# ==========================================
def format_gene_symbols(symbol_str):
    """
    将混乱的 Gene Symbol 格式化为标准化格式: "sym1";"sym2"
    支持处理逗号(,)、竖线(|) 等常见分隔符
    """
    if pd.isna(symbol_str) or str(symbol_str).strip() in ('', '-'):
        return ""
    
    # 替换各种可能的括号和不需要的字符
    clean_str = str(symbol_str).replace('*', '')
    
    # 使用正则按逗号或竖线分割
    symbols = re.split(r'[,|]', clean_str)
    
    # 清理空格并加上双引号，过滤掉空字符串
    formatted_symbols = [f'"{s.strip()}"' for s in symbols if s.strip()]
    
    return ";".join(formatted_symbols)

def get_ontology_type(onto_id):
    """根据 ID 前缀判断 Ontology 类型"""
    if pd.isna(onto_id): return ""
    if onto_id.startswith('GO'): return 'GO'
    if onto_id.startswith('TO'): return 'TO'
    if onto_id.startswith('PO'): return 'PO' 
    return 'Unknown'

def load_protein_mapping(filepath):
    """
    加载本地的 protein_gene_mapping.txt
    构建 Protein/Transcript ID 到 RAP ID 的映射字典
    """
    print(f"Loading protein mapping dictionary from: {filepath}")
    # 读取时处理可能存在的双引号
    df = pd.read_csv(filepath, sep='\t', quotechar='"')
    
    mapping_dict = {}
    for _, row in df.iterrows():
        rap_id = str(row['RAP_ID']).strip()
        ext_id = str(row['Protein_or_Transcript_ID']).strip()
        if ext_id and rap_id and ext_id != 'nan':
            mapping_dict[ext_id] = rap_id
            
    return mapping_dict

# ==========================================
# 2. 各数据库处理模块
# ==========================================

def process_oryzabase(filepath):
    """处理 Oryzabase 数据，同时返回 Gramene->RAP ID 映射字典"""
    print(f"Processing Oryzabase: {filepath}...")
    df = pd.read_csv(filepath, sep='\t')
    
    # 构建 Gramene ID 到 RAP ID 的映射字典
    valid_mapping = df.dropna(subset=['RAP ID'])
    gramene_to_rap = {}
    for _, row in valid_mapping.iterrows():
        rap_id = str(row['RAP ID']).strip()
        gramene_id = str(row['Gramene ID']).strip()
        if gramene_id and gramene_id != 'nan':
            gramene_to_rap[gramene_id] = rap_id.split(',')[0].strip()
    
    gta_records = []
    df_valid = df.dropna(subset=['RAP ID'])
    
    for _, row in df_valid.iterrows():
        rap_id = str(row['RAP ID']).split(',')[0].strip()
        
        # 收集所有的 symbols
        raw_symbols = []
        if pd.notna(row.get('CGSNL Gene Symbol')): raw_symbols.append(str(row['CGSNL Gene Symbol']))
        if pd.notna(row.get('Gene symbol synonym(s)')): raw_symbols.append(str(row['Gene symbol synonym(s)']))
        symbol_fmt = format_gene_symbols(",".join(raw_symbols))
        
        # 解析本体字段 (GO, TO, PO)
        onto_columns = ['Gene Ontology', 'Trait Ontology', 'Plant Ontology']
        for col in onto_columns:
            cell_data = row.get(col)
            if pd.isna(cell_data): continue
            
            items = str(cell_data).split(',')
            for item in items:
                match = re.search(r'([GTP]O:\d+)\s*-\s*(.*)', item.strip())
                if match:
                    onto_id = match.group(1)
                    desc = match.group(2).strip()
                    gta_records.append({
                        'RAP_ID': rap_id,
                        'Gene_Symbol': symbol_fmt,
                        'Ontology_Type': get_ontology_type(onto_id),
                        'Ontology_ID': onto_id,
                        'Trait_Description': desc,
                        'Evidence_Code': 'Oryzabase_Curated',
                        'Source_DB': 'Oryzabase',
                        'Reference': '',
                        'Original_ID': rap_id
                    })
                    
    return pd.DataFrame(gta_records), gramene_to_rap

def process_rapdb(filepath):
    """处理 RAP-DB 代表性注释数据"""
    print(f"Processing RAP-DB: {filepath}...")
    df = pd.read_csv(filepath, sep='\t')
    gta_records = []
    
    for _, row in df.iterrows():
        rap_id = str(row['Locus_ID']).strip()
        
        raw_symbols = []
        for col in ['CGSNL Gene Symbol', 'RAP-DB Gene Symbol Synonym(s)', 'Oryzabase Gene Symbol Synonym(s)']:
            if pd.notna(row.get(col)):
                raw_symbols.append(str(row[col]))
        symbol_fmt = format_gene_symbols(",".join(raw_symbols))
        
        go_data = row.get('GO')
        pmid = str(row.get('Literature PMID')) if pd.notna(row.get('Literature PMID')) else ''
        
        if pd.notna(go_data):
            go_items = go_data.split('),')
            for item in go_items:
                item = item + ')' if not item.endswith(')') else item
                match = re.search(r'(.*?):\s*(.*?)\s*\((GO:\d+)\)', item)
                if match:
                    desc = match.group(2).strip()
                    go_id = match.group(3).strip()
                    gta_records.append({
                        'RAP_ID': rap_id,
                        'Gene_Symbol': symbol_fmt,
                        'Ontology_Type': 'GO',
                        'Ontology_ID': go_id,
                        'Trait_Description': desc,
                        'Evidence_Code': 'RAP-DB_Curated',
                        'Source_DB': 'RAP-DB',
                        'Reference': f"PMID:{pmid}" if pmid and pmid != 'nan' else '',
                        'Original_ID': rap_id
                    })
                    
    return pd.DataFrame(gta_records)

def process_ensembl(filepath):
    """处理 Ensembl 数据"""
    print(f"Processing Ensembl: {filepath}...")
    df = pd.read_csv(filepath, sep='\t')
    
    # 过滤非 Os 开头的 ID
    df = df[df['RAP_ID'].astype(str).str.startswith('Os')]
    
    df_out = pd.DataFrame({
        'RAP_ID': df['RAP_ID'],
        'Gene_Symbol': '',
        'Ontology_Type': 'GO',
        'Ontology_ID': df['GO_ID'],
        'Trait_Description': df['Function_Description'],
        'Evidence_Code': df['Evidence_Code'],
        'Source_DB': 'Ensembl_' + df['Source_DB'].astype(str),
        'Reference': '',
        'Original_ID': df['RAP_ID']
    })
    return df_out

def process_planteome(directory, gramene_to_rap_dict, protein_to_rap_dict):
    """处理 Planteome 数据，引入外部蛋白 ID 的双重映射"""
    print(f"Processing Planteome directory: {directory}...")
    gta_records = []
    
    for filename in os.listdir(directory):
        if not filename.endswith('.assoc'): continue
        filepath = os.path.join(directory, filename)
        
        onto_type = 'PO'
        if 'anatomy' in filename: onto_type = 'PO_Anatomy'
        elif 'growth' in filename: onto_type = 'PO_Growth'
        elif 'to_gene' in filename or 'to_protein' in filename: onto_type = 'TO'
        
        try:
            df = pd.read_csv(filepath, sep='\t', comment='!', header=None, dtype=str)
        except Exception as e:
            print(f"  Skipping {filename}: {e}")
            continue
            
        for _, row in df.iterrows():
            if len(row) < 10: continue
            
            orig_id = str(row[1]).strip()
            with_from = str(row[7]).strip()
            rap_id = None
            
            # --- 核心映射逻辑 (双保险) ---
            if orig_id.startswith('Os'):
                rap_id = orig_id
            elif orig_id.startswith('GR:'):
                rap_id = gramene_to_rap_dict.get(orig_id, None)
            
            if not rap_id and orig_id in protein_to_rap_dict:
                rap_id = protein_to_rap_dict[orig_id]
                
            if not rap_id and with_from and with_from != 'nan':
                clean_protein_id = with_from.split(':')[-1] 
                if clean_protein_id in protein_to_rap_dict:
                    rap_id = protein_to_rap_dict[clean_protein_id]
            # ---------------------------
            
            if not rap_id:
                continue
                
            symbol_fmt = format_gene_symbols(row[2])
            onto_id = str(row[4]).strip()
            ref_id = str(row[5]).strip()
            evd_code = str(row[6]).strip()
            desc = str(row[9]).strip()
            
            gta_records.append({
                'RAP_ID': rap_id,
                'Gene_Symbol': symbol_fmt,
                'Ontology_Type': onto_type,
                'Ontology_ID': onto_id,
                'Trait_Description': desc,
                'Evidence_Code': evd_code,
                'Source_DB': f'Planteome_{filename}',
                'Reference': ref_id,
                'Original_ID': orig_id
            })
            
    return pd.DataFrame(gta_records)


# ==========================================
# 3. 主程序流水线
# ==========================================
if __name__ == "__main__":
    # --- 文件路径配置 ---
    base_dir = str(GTA_DIR.parent)
    oryzabase_file = os.path.join(str(STANDARD_GENE_DIR), "OryzabaseGeneListEn_20250702010110.txt")
    rapdb_file = os.path.join(str(GTA_OTHER_DB_DIR), "IRGSP-1.0_representative_annotation_2025-03-19_RAP-DB.tsv")
    ensembl_file = os.path.join(str(GTA_OTHER_DB_DIR), "Ensembl_GTA.txt")
    planteome_dir = os.path.join(str(GTA_OTHER_DB_DIR), "Planteome")
    output_file = os.path.join(str(GTA_DIR), "Unified_Rice_GTA_Database.tsv")
    protein_mapping_file = os.path.join(planteome_dir, "protein_gene_mapping.txt")
    # ----------------------------------

    # 1. 提取 Oryzabase 并获取 Gramene 映射字典
    df_oryza, gramene_to_rap_map = process_oryzabase(oryzabase_file)
    print(f"Extracted {len(df_oryza)} rows from Oryzabase.")
    print(f"Built Gramene -> RAP ID map with {len(gramene_to_rap_map)} entries.")

    # 2. 提取 RAP-DB
    df_rapdb = process_rapdb(rapdb_file)
    print(f"Extracted {len(df_rapdb)} rows from RAP-DB.")

    # 3. 提取 Ensembl
    df_ensembl = process_ensembl(ensembl_file)
    print(f"Extracted {len(df_ensembl)} rows from Ensembl.")

    # 4. 加载 Protein 映射字典，并提取 Planteome 数据
    protein_map = load_protein_mapping(protein_mapping_file)
    print(f"Built Protein -> RAP ID map with {len(protein_map)} entries.")
    
    df_planteome = process_planteome(planteome_dir, gramene_to_rap_map, protein_map)
    print(f"Extracted {len(df_planteome)} rows from Planteome.")

    # 5. 整合与后处理
    print("Merging all databases...")
    all_gta_df = pd.concat([df_oryza, df_rapdb, df_ensembl, df_planteome], ignore_index=True)
    
    # 基础去重
    all_gta_df = all_gta_df.drop_duplicates(subset=['RAP_ID', 'Ontology_ID', 'Evidence_Code'], keep='first')
    
    # 确保缺失值为 ""
    all_gta_df['Gene_Symbol'] = all_gta_df['Gene_Symbol'].fillna("")
    
    # 使用 csv.QUOTE_NONE 禁用 Pandas 自动转义双引号，使用 escapechar 防止制表符干扰
    all_gta_df.to_csv(output_file, sep='\t', index=False, quoting=csv.QUOTE_NONE, escapechar='\\')
    
    print(f"Successfully built Unified GTA Database! Total unique records: {len(all_gta_df)}")
    print(f"Saved to: {output_file}")
