# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""
脚本功能：
    本脚本用于分析“补充基因字典 (Supplementary Gene Dictionary)”中的新基因 (Novel Genes) 来源。
    它通过对比 Oryzabase 官方基因库，排除掉已有的基因及其变体（基于子串匹配逻辑），
    进而统计这些“真正的新发现基因”在文献中的时间分布（特别是近 5 年的占比）以及来源期刊的排名。

输入文件：
    1. oryzabase_gene_oger_dict.tsv: Oryzabase 官方基因字典，作为基准库。
    2. supplementary_gene_oger_dict.tsv: 待检测的补充基因字典，包含基因 ID 和名称。
    3. supplementary_gene_samples.jsonl: 样本元数据，包含 validation_target_id、year 和 journal。

输出信息：
    1. 控制台输出总的新基因样本数。
    2. 近 5 年（2021-2026）内发表的新基因占比。
    3. 发表新基因数量排名前 15 的期刊列表。
"""


import json
import os
import sys
from collections import Counter

# --- 路径配置（统一由 ricemind_config.py 管理）---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import RESULTS_DIR, SUPP_DICT_DIR

dict_dir = str(SUPP_DICT_DIR)
oryza_dict_path = os.path.join(dict_dir, 'oryzabase_gene_oger_dict.tsv')
supp_dict_path = os.path.join(dict_dir, 'supplementary_gene_oger_dict.tsv')
samples_path = os.environ.get(
    'RICEMIND_SUPP_SAMPLES', str(RESULTS_DIR / 'supplementary_gene_samples.jsonl')
)

# 1. 加载 Oryzabase 基因库用于排查
print("加载 Oryzabase 字典...")
oryza_names_lower = set()
with open(oryza_dict_path, 'r', encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            names = [n.strip().lower() for n in parts[3].split(',')]
            for n in names:
                if len(n) >= 3:
                    oryza_names_lower.add(n)

# 2. 加载 Supplementary 字典映射
print("加载 Supplementary 字典...")
supp_id_to_names = {}
with open(supp_dict_path, 'r', encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            gene_id = parts[2]
            gene_name = parts[3]
            if gene_id not in supp_id_to_names:
                supp_id_to_names[gene_id] = set()
            supp_id_to_names[gene_id].add(gene_name)

# 3. 扫描样本并分析 Novel Genes
print("正在分析 Novel Genes 的文献来源...")
novel_genes_years = []
novel_genes_journals = []
recent_years_threshold = 2021 # 定义近 5 年为 2021 及以后

with open(samples_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        target_id = data.get('validation_target_id')
        
        if not target_id or target_id not in supp_id_to_names:
            continue
            
        # 判定是否为 Novel Gene (非子串变体)
        names = supp_id_to_names[target_id]
        is_variant = False
        for supp_name in names:
            supp_name_lower = supp_name.lower()
            if len(supp_name_lower) < 4:
                continue
            for o_name in oryza_names_lower:
                if supp_name_lower in o_name or o_name in supp_name_lower:
                    is_variant = True
                    break
            if is_variant:
                break
                
        # 如果是全新的未收录基因
        if not is_variant:
            year_str = data.get('year', '0')
            journal = data.get('journal', 'Unknown')
            try:
                year = int(year_str)
                novel_genes_years.append(year)
                # 简单清洗期刊名称以便统计
                journal_clean = journal.split('.')[0].strip() if journal else 'Unknown'
                novel_genes_journals.append(journal_clean)
            except ValueError:
                continue

# 4. 统计输出
total_novel = len(novel_genes_years)
recent_novel = sum(1 for y in novel_genes_years if y >= recent_years_threshold)
recent_pct = (recent_novel / total_novel) * 100 if total_novel > 0 else 0

print("\n=== 新基因 (Novel Genes) 文献来源统计 ===")
print(f"总计分析了 {total_novel} 个全新基因样本。")
print(f"其中来自近 5 年 ({recent_years_threshold}-2026) 的文献有: {recent_novel} 个 ({recent_pct:.2f}%)")

print("\n排名前 15 的期刊分布:")
top_journals = Counter(novel_genes_journals).most_common(15)
for j, count in top_journals:
    print(f" - {j}: {count} 个")
