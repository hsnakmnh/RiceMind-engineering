# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
import pandas as pd
import gzip
import json
import re
import os
import sys

"""
=========================================================================================
Script Name: extract_multi_omics_data.py (或您的实际文件名)
Description: 水稻多组学序列与基因组坐标全景提取流水线 (Multi-omics Sequence & Coordinate Extraction Pipeline)
Author: [您的名字/实验室]
Date: [当前日期]

【脚本功能概述】
本脚本旨在弥合“平面化的基因注释文本”与“立体的生物大分子序列”之间的鸿沟。
通过将 Oryzabase 的标准注释信息与 Ensembl (IRGSP-1.0) 的底层基因组序列数据深度融合，
脚本自动化地提取了水稻基因的物理坐标（Coordinates），并精准截取了对应的基因组 DNA、
转录本序列（cDNA）以及翻译产物（Protein）序列。最终生成一个高度结构化、包含完整检索
索引的多组学 JSON 数据库（rice_multi_omics.json），为下游的基因功能预测、
引物设计及大语言模型（LLM）驱动的序列分析提供底层数据支撑。

【数据处理流水线 (Pipeline Logic)】
本脚本的处理逻辑分为四个严密的模块：

1. 基础载荷与同义词索引构建 (Base Structure & Indexing):
   - 解析 Oryzabase 官方列表，以 RAP ID 为核心节点构建基础数据字典（Payload）。
   - 提取 CGSNL Symbol 及所有同义词，构建倒排检索树（Search Index），支持多别名映射。
   - 预设三大权威数据库（RAP-DB, Ensembl, Gramene）的访问路由（External Links）。

2. 基因组坐标定位与序列截取 (Genomic Coordinates & DNA Extraction) - [生物信息学核心步骤]:
   - 坐标解析：遍历 GFF3 基因组注释文件，精准抓取基因级别（gene feature）的起止物理坐标及链向（Strand）。
   - 序列截取：基于坐标对全基因组 FASTA 文件进行切片。
   - 负链校正：考虑到 GFF3 为 1-based 坐标系，且负链（- strand）基因的实际读取方向与参考基因组相反，
     本模块调用 Biopython 的 `reverse_complement()` 对负链序列进行自动反向互补校正，确保提取的 DNA 
     序列与实际转录方向严格一致。

3. 转录组与蛋白质组数据挂载 (Transcriptome & Proteome Integration):
   - 读取 cDNA 与 Protein 的 FASTA 文件，利用序列描述（Description）中的 `gene:Os...` 标签
     将转录本层级（Transcript ID）的序列精确挂载到其父级基因（RAP ID）下。
   - 形成 [Gene] -> [Multiple Transcripts] -> [cDNA & Protein Sequences] 的层级结构。

4. 数据清洗与质量控制 (Quality Control):
   - 遍历生成的 API 数据库，剔除未匹配到任何序列（无 DNA 且无转录本）的“空壳”基因实体。
   - 同步清理废弃实体在 Search Index 中的残留节点，确保最终 JSON 的纯净度和查询效率。

【输出数据结构 (JSON Schema)】
{
    "search_index": { "sd1": ["Os01g0883800"], ... },
    "gene_payload": {
        "Os01g0883800": {
            "rap_id": "Os01g0883800",
            "primary_symbol": "SD1",
            "location": { "chromosome": "1", "start": 38382382, "end": 38385504, "strand": "+" },
            "external_links": { ... },
            "genomic_seq": "ATGC...",
            "transcripts": [
                { "transcript_id": "Os01t0883800-01", "cdna_seq": "ATGC...", "protein_seq": "M..." }
            ]
        }
    }
}
=========================================================================================
"""




from Bio import SeqIO
from collections import defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import SEQUENCE_DATA_DIR

# 1. 配置文件路径（统一由 ricemind_config.py 管理）
BASE_DIR = str(SEQUENCE_DATA_DIR)
ORYZABASE_FILE = os.path.join(BASE_DIR, "OryzabaseGeneListEn_20250702010110.txt")
OUTPUT_JSON = os.path.join(BASE_DIR, "rice_multi_omics.json")

GFF3_FILE = os.path.join(BASE_DIR, "Oryza_sativa.IRGSP-1.0.59.gff3.gz")
DNA_FILE = os.path.join(BASE_DIR, "Oryza_sativa.IRGSP-1.0.dna.toplevel.fa.gz")
CDNA_FILE = os.path.join(BASE_DIR, "Oryza_sativa.IRGSP-1.0.cdna.all.fa.gz")
PEP_FILE = os.path.join(BASE_DIR, "Oryza_sativa.IRGSP-1.0.pep.all.fa.gz")

def clean_str(val):
    if pd.isna(val) or str(val).strip().lower() == 'nan':
        return ""
    return str(val).strip()

def build_base_structure(oryzabase_path):
    """解析 Oryzabase 构建多对多索引树和基础载荷"""
    print("1. 正在解析 Oryzabase 构建索引树...")
    df = pd.read_csv(oryzabase_path, sep='\t', encoding='utf-8', on_bad_lines='skip', dtype=str)

    search_index_temp = defaultdict(set)
    gene_payload = {}

    for _, row in df.iterrows():
        rap_id_raw = clean_str(row.get('RAP ID'))
        if not rap_id_raw:
            continue

        rap_list = [r.strip() for r in rap_id_raw.split(',') if r.strip()]
        
        cgsnl_symbol = clean_str(row.get('CGSNL Gene Symbol'))
        cgsnl_name = clean_str(row.get('CGSNL Gene Name'))
        symbol_synonyms = clean_str(row.get('Gene symbol synonym(s)'))
        name_synonyms = clean_str(row.get('Gene name synonym(s)'))

        search_terms = []
        if cgsnl_symbol: search_terms.append(cgsnl_symbol)
        if cgsnl_name: search_terms.append(cgsnl_name)
        if symbol_synonyms: search_terms.extend([s.strip() for s in symbol_synonyms.split(',')])
        if name_synonyms: search_terms.extend([s.strip() for s in name_synonyms.split(',')])

        for rap_id in rap_list:
            if rap_id not in gene_payload:
                gene_payload[rap_id] = {
                    "rap_id": rap_id,
                    "primary_symbol": cgsnl_symbol or "Unknown",
                    "all_symbols": list(set([cgsnl_symbol] + [s.strip() for s in symbol_synonyms.split(',') if s.strip()])) if cgsnl_symbol or symbol_synonyms else [],
                    "all_names": list(set([cgsnl_name] + [s.strip() for s in name_synonyms.split(',') if s.strip()])) if cgsnl_name or name_synonyms else [],
                    "location": None, # 预留位置信息字段
                    # === 新增：权威数据库外链字典 ===
                    "external_links": {
                        "RAP-DB": f"https://rapdb.dna.affrc.go.jp/locus/?name={rap_id}",
                        "Ensembl_Plants": f"https://plants.ensembl.org/Oryza_sativa/Gene/Summary?g={rap_id}",
                        "Gramene": f"https://ensembl.gramene.org/Oryza_sativa/Gene/Summary?g={rap_id}"
                    },
                    # ==============================
                    "genomic_seq": None,
                    "transcripts": []
                }
            
            search_terms.append(rap_id)

            for term in search_terms:
                if term:
                    cleaned_term = term.lower().replace('[', '').replace(']', '').strip()
                    search_index_temp[cleaned_term].add(rap_id)

    search_index = {k: list(v) for k, v in search_index_temp.items()}
    return {"search_index": search_index, "gene_payload": gene_payload}

def append_genomic_dna_and_location(api_db):
    """解析 GFF3 提取坐标、写入位置信息并截取序列"""
    print(f"2. 正在解析 GFF3 提取基因组坐标 ({os.path.basename(GFF3_FILE)})...")
    coords_dict = {}
    
    with gzip.open(GFF3_FILE, 'rt') as f:
        for line in f:
            if line.startswith('#'): continue
            parts = line.strip().split('\t')
            # 确保提取的是 gene 级别的特征
            if len(parts) < 9 or parts[2] != 'gene': continue
            
            match = re.search(r'ID=gene:(Os\d+g\d+)', parts[8])
            if match:
                rap_id = match.group(1)
                if rap_id in api_db["gene_payload"]:
                    # 记录物理坐标
                    coords = {
                        "chromosome": parts[0],
                        "start": int(parts[3]),
                        "end": int(parts[4]),
                        "strand": parts[6]
                    }
                    coords_dict[rap_id] = coords
                    # 将位置信息写入最终的 JSON 载荷中
                    api_db["gene_payload"][rap_id]["location"] = coords

    print(f"3. 正在读取全基因组 FASTA 并截取对应序列 ({os.path.basename(DNA_FILE)})...")
    genome = {}
    with gzip.open(DNA_FILE, "rt") as handle:
        for rec in SeqIO.parse(handle, "fasta"):
            genome[rec.id] = rec.seq

    extracted_count = 0
    for rap_id, coords in coords_dict.items():
        if coords["chromosome"] in genome:
            # GFF3 是 1-based，Python 是 0-based，需要 -1
            seq = genome[coords["chromosome"]][coords["start"]-1 : coords["end"]]
            
            # 生物信息学核心逻辑：负链自动反向互补
            if coords["strand"] == '-':
                seq = seq.reverse_complement()
                
            api_db["gene_payload"][rap_id]["genomic_seq"] = str(seq)
            extracted_count += 1
            
    print(f"   成功为 {extracted_count} 个基因匹配了位置信息并截取了 DNA 序列。")
    return api_db

def append_transcript_omics(api_db):
    """解析 cDNA 和 Protein 补充转录本序列"""
    print(f"4. 正在解析 cDNA 文件 ({os.path.basename(CDNA_FILE)})...")
    with gzip.open(CDNA_FILE, "rt") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            match = re.search(r'gene:(Os\d+g\d+)', record.description)
            if match:
                rap_id = match.group(1)
                if rap_id in api_db["gene_payload"]:
                    api_db["gene_payload"][rap_id]["transcripts"].append({
                        "transcript_id": record.id,
                        "cdna_seq": str(record.seq),
                        "protein_seq": None
                    })

    print(f"5. 正在解析 Protein 文件 ({os.path.basename(PEP_FILE)})...")
    with gzip.open(PEP_FILE, "rt") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            match = re.search(r'gene:(Os\d+g\d+)', record.description)
            if match:
                rap_id = match.group(1)
                if rap_id in api_db["gene_payload"]:
                    for transcript in api_db["gene_payload"][rap_id]["transcripts"]:
                        if transcript["transcript_id"] == record.id:
                            transcript["protein_seq"] = str(record.seq)
                            break
    return api_db

def main():
    api_db = build_base_structure(ORYZABASE_FILE)
    api_db = append_genomic_dna_and_location(api_db)
    api_db = append_transcript_omics(api_db)

    print("\n6. 正在清理未匹配到任何序列的空壳实体...")
    valid_payload = {}
    valid_raps = set()
    
    for rap_id, data in api_db["gene_payload"].items():
        if data["genomic_seq"] is not None or len(data["transcripts"]) > 0:
            valid_payload[rap_id] = data
            valid_raps.add(rap_id)
            
    api_db["gene_payload"] = valid_payload
    
    cleaned_search_index = {}
    for term, raps in api_db["search_index"].items():
        valid_mapped_raps = [r for r in raps if r in valid_raps]
        if valid_mapped_raps:
            cleaned_search_index[term] = valid_mapped_raps
            
    api_db["search_index"] = cleaned_search_index

    print("7. 保存最终包含完整位置和序列的 API JSON 数据库...")
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(api_db, f, indent=4)

    print(f"\n✅ 完成！最终生成 {len(api_db['gene_payload'])} 个有效基因实体。")
    print(f"数据已保存至: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
