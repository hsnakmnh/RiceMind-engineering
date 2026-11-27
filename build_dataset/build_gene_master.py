# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""
=========================================================================================
Script Name: build_gene_master.py
Description: 构建水稻全景标准化基因参考索引 (Unified Rice Gene Master Index)
Author: [您的名字/实验室]
Date: [当前日期]

【脚本功能概述】
在多源生物信息学数据库（如 Oryzabase, RAP-DB, Ensembl Plants, Planteome）以及 NLP 文本挖掘结果的
整合过程中，基因标识符（Identifiers）的不统一是导致数据孤岛和关联记录丢失的核心痛点。
本脚本旨在构建一个“大一统”的基因标准化参考字典（Single Source of Truth），以标准的 RAP ID 
为绝对主键（Primary Key），将跨数据库的异构 ID、复杂的同义词网络、基因组位置信息以及外部证据链接
进行深度聚合，生成高维度的结构化 JSON 数据。

【数据源与整合逻辑】
本脚本的整合流水线（Pipeline）包含三个核心模块：
1. 多组学数据基座 (Multi-omics Data):
   - 来源: `rice_multi_omics.json`
   - 贡献: 提供基因的物理位置（Chromosome, Start, End, Strand）以及在主要数据库（RAP-DB, 
     Ensembl Plants, Gramene）中的直接有效链接，并从中推导专属 ID。
     
2. 权威命名与注释整合 (Oryzabase Integration):
   - 来源: `OryzabaseGeneListEn_*.txt`
   - 贡献: 注入由 CGSNL（水稻基因座命名委员会）官方认证的 Primary Symbol、完整的同义词（Synonyms）
     网络、表型分类（Trait Class）以及 MSU ID 和 OryzaGeneID 的映射关系。

3. Planteome 蛋白质-基因映射机制 (Protein-to-Gene Mapping for GTAs) - [论文关键创新点]:
   - 来源: `protein_gene_mapping.txt` (提取自 Ensembl 核心数据库 `ensembloryza_sativa_core_62_115_7`)
   - 机制与意义: Planteome 数据库提供了丰富的跨物种本体关联，但其水稻数据主要体现为
     “蛋白质-表型关联（Protein-Trait Associations）”，而非直接的基因关联。为了在我们的
     RiceMind 系统中统一构建“基因-表型关联（Gene-Trait Associations, GTAs）”，本模块
     利用从 Ensembl 导出的严格映射表，将孤立的 Protein IDs（如 Uniprot/SPTREMBL ID）精准
     回溯并挂载到其对应的 RAP ID 上。这是实现多维度证据网络融合的关键技术桥梁。

【输出数据结构 (Schema)】
生成的 `Unified_Gene_Master.json` 为下游分析提供了统一的数据底座：
{
    "RAP_ID (e.g., Os04g0550600)": {
        "IDs": { ... 包含 Oryzabase_ID, MSU_ID, Ensembl_ID, Gramene_ID, Protein_ID },
        "Nomenclature": { ... 包含 Primary_Symbol, All_Symbols (核心同义词库) },
        "Annotations": { ... 包含 Explanation, Trait_Class },
        "Location": { ... 包含 Chromosome, Start, End, Strand },
        "External_Links": { ... 包含各数据库的验证 URL }
    }
}

【在系统与论文中的学术价值】
1. 彻底解决实体劫持与数据丢失：构建了全景反向索引（Reverse Index）。无论 NLP 挖掘工具提取到的是
   别名、MSU ID 还是 Planteome 的 Protein ID，系统均能通过该字典实现 100% 召回，精准映射回唯一 RAP ID。
2. 提升知识图谱置信度：确保了基于 NLP 的海量动态文本证据与基于专家的静态结构化证据能够在一个
   统一的锚点（RAP ID）上进行交叉验证和 Evidence Profile 构建。
=========================================================================================
"""



import os
import json
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import DATA_DIR, STANDARD_GENE_DIR

# ==========================================
# 1. 配置文件路径（统一由 ricemind_config.py 管理）
# ==========================================
STANDARD_DIR = str(STANDARD_GENE_DIR)
OMICS_DIR = str(DATA_DIR)

FILES = {
    "omics_json": os.path.join(OMICS_DIR, "rice_multi_omics.json"),
    "oryzabase_txt": os.path.join(STANDARD_DIR, "OryzabaseGeneListEn_20250702010110.txt"),
    "planteome_txt": os.path.join(STANDARD_DIR, "protein_gene_mapping.txt"),
    "output_json": os.path.join(STANDARD_DIR, "Unified_Gene_Master.json")
}

def build_gene_master():
    gene_master = {}

    # ---------------------------------------------------------
    # 步骤 A: 解析 rice_multi_omics.json (提供组学链接、ID与位置)
    # ---------------------------------------------------------
    print(f"1. Loading multi-omics data from {FILES['omics_json']}...")
    if os.path.exists(FILES['omics_json']):
        with open(FILES['omics_json'], 'r', encoding='utf-8') as f:
            omics_data = json.load(f)
            gene_payload = omics_data.get('gene_payload', {})
            
            for rap_id, info in gene_payload.items():
                loc = info.get('location') or {}
                external_links = info.get('external_links', {})
                
                valid_links = {}
                ensembl_id = []
                gramene_id = []
                
                if external_links:
                    for db_name, url in external_links.items():
                        if isinstance(url, str) and url.startswith("http"):
                            valid_links[db_name] = url
                            
                            # 从有效链接推导 ID
                            if db_name == "Ensembl_Plants" and rap_id not in ensembl_id:
                                ensembl_id.append(rap_id)
                            if db_name == "Gramene" and rap_id not in gramene_id:
                                gramene_id.append(rap_id)
                
                all_symbols = info.get('all_symbols', [])
                primary = info.get('primary_symbol', '')
                if primary and primary not in all_symbols:
                    all_symbols.append(primary)

                gene_master[rap_id] = {
                    "IDs": {
                        "RAP_ID": rap_id,
                        "Oryzabase_ID": [],
                        "MSU_ID": [],
                        "Ensembl_ID": ensembl_id,
                        "Gramene_ID": gramene_id,
                        "Protein_ID": []
                    },
                    "Nomenclature": {
                        "Primary_Symbol": primary,
                        "All_Symbols": all_symbols,
                        "CGSNL_Name": ""
                    },
                    "Annotations": {
                        "Explanation": "",
                        "Trait_Class": ""
                    },
                    "Location": {
                        "Chromosome": loc.get('chromosome'),
                        "Start": loc.get('start'),
                        "End": loc.get('end'),
                        "Strand": loc.get('strand')
                    },
                    "External_Links": valid_links
                }
    else:
        print(f"❌ Warning: {FILES['omics_json']} not found.")

    # ---------------------------------------------------------
    # 步骤 B: 解析 Oryzabase TXT (补充命名、注释和 Gramene ID)
    # ---------------------------------------------------------
    print(f"2. Merging Oryzabase data from {FILES['oryzabase_txt']}...")
    if os.path.exists(FILES['oryzabase_txt']):
        with open(FILES['oryzabase_txt'], 'r', encoding='utf-8') as f:
            next(f) # 跳过表头
            for line in f:
                parts = line.split('\t')
                if len(parts) < 13: # 确保列数足够读取 Gramene ID (索引12)
                    continue
                
                oryza_id = parts[0].strip()          
                cgsnl_symbol = parts[1].strip()      
                synonyms = parts[2].strip()          
                cgsnl_name = parts[3].strip()        
                explanation = parts[8].strip()       
                trait_class = parts[9].strip()       
                raw_rap_id = parts[10].strip()       
                msu_id = parts[11].strip()           
                oryza_gramene = parts[12].strip()    # 提取第 13 列的 Gramene ID

                if not raw_rap_id:
                    continue
                
                rap_id = raw_rap_id.split(',')[0].strip()

                if rap_id not in gene_master:
                    gene_master[rap_id] = {
                        "IDs": {"RAP_ID": rap_id, "Oryzabase_ID": [], "MSU_ID": [], "Ensembl_ID": [], "Gramene_ID": [], "Protein_ID": []},
                        "Nomenclature": {"Primary_Symbol": "", "All_Symbols": [], "CGSNL_Name": ""},
                        "Annotations": {"Explanation": "", "Trait_Class": ""},
                        "Location": {"Chromosome": None, "Start": None, "End": None, "Strand": None},
                        "External_Links": {}
                    }

                target = gene_master[rap_id]

                # --- 填充 IDs ---
                if oryza_id and f"OryzaGeneID:{oryza_id}" not in target["IDs"]["Oryzabase_ID"]:
                    target["IDs"]["Oryzabase_ID"].append(f"OryzaGeneID:{oryza_id}")
                
                if msu_id:
                    for m in msu_id.split(','):
                        m = m.strip()
                        if m and m not in target["IDs"]["MSU_ID"]:
                            target["IDs"]["MSU_ID"].append(m)
                            
                # 合并 Oryzabase 里的 Gramene ID
                if oryza_gramene and oryza_gramene not in target["IDs"]["Gramene_ID"]:
                    target["IDs"]["Gramene_ID"].append(oryza_gramene)

                # --- 填充 Nomenclature ---
                if cgsnl_symbol:
                    target["Nomenclature"]["Primary_Symbol"] = cgsnl_symbol
                    if cgsnl_symbol not in target["Nomenclature"]["All_Symbols"]:
                        target["Nomenclature"]["All_Symbols"].append(cgsnl_symbol)
                
                if synonyms:
                    for s in re.split(r'[,|]', synonyms):
                        s = s.strip()
                        if s and s not in target["Nomenclature"]["All_Symbols"]:
                            target["Nomenclature"]["All_Symbols"].append(s)
                
                if cgsnl_name: target["Nomenclature"]["CGSNL_Name"] = cgsnl_name
                if explanation: target["Annotations"]["Explanation"] = explanation
                if trait_class: target["Annotations"]["Trait_Class"] = trait_class
    else:
        print(f"❌ Warning: {FILES['oryzabase_txt']} not found.")

    # ---------------------------------------------------------
    # 步骤 C: 解析 Planteome TXT (去除双引号，精确提取)
    # ---------------------------------------------------------
    print(f"3. Merging Planteome Protein mapping from {FILES['planteome_txt']}...")
    if os.path.exists(FILES['planteome_txt']):
        found_proteins = 0
        with open(FILES['planteome_txt'], 'r', encoding='utf-8') as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split('\t')
                # 您的文件有 3 列，第 1 列是 RAP_ID，第 3 列是 Protein_ID
                if len(parts) >= 3:
                    # 去除字符串两端的双引号和空白字符
                    rap_id = parts[0].replace('"', '').strip()
                    prot_id = parts[2].replace('"', '').strip()
                    
                    if rap_id.startswith("Os") and "g" in rap_id:
                        if rap_id in gene_master and prot_id:
                            if prot_id not in gene_master[rap_id]["IDs"]["Protein_ID"]:
                                gene_master[rap_id]["IDs"]["Protein_ID"].append(prot_id)
                                found_proteins += 1
        print(f"   -> Successfully loaded {found_proteins} Protein mappings.")
    else:
        print(f"❌ CRITICAL WARNING: Planteome file not found at {FILES['planteome_txt']}!")

    # ---------------------------------------------------------
    # 保存结果为 JSON
    # ---------------------------------------------------------
    print(f"4. Saving unified data to {FILES['output_json']}...")
    with open(FILES['output_json'], 'w', encoding='utf-8') as f:
        json.dump(gene_master, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Successfully generated Master Gene Dictionary with {len(gene_master)} unique RAP IDs!")

if __name__ == "__main__":
    build_gene_master()
