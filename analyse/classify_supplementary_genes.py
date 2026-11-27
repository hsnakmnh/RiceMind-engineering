# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""
脚本功能：
    本脚本用于对文献中提取的“补充基因 (Supplementary Genes)”进行全局的分类与评估。
    它提取样本中出现的所有补充基因 ID，并将其与 Oryzabase 官方基因字典进行交叉比对。
    基于双向子串匹配逻辑（长度 >= 4），将基因划分为两大类：
    1. Variants / Family Names (变体/家族泛称)：与官方基因存在包含关系，说明是对已有基因的别名或家族扩展。
    2. Uncatalogued Novel Genes (全新基因)：与官方基因完全无重叠，说明是数据库存在滞后而未收录的全新发现。
    最终生成一份详细的分类统计与明细报告。

输入文件：
    1. supplementary_gene_samples.jsonl: 已提取的补充基因样本数据，用于获取实际在文献中出现的基因 ID (validation_target_id)。
    2. supplementary_gene_oger_dict.tsv: 补充基因字典，用于将提取到的 ID 映射回具体的基因名称。
    3. oryzabase_gene_oger_dict.tsv: Oryzabase 官方基因字典，作为分类比对的基准库。

输出信息：
    1. 控制台进度提示与最终的分类占比概览。
    2. gene_classification_report.txt: 详细的纯文本报告，包含总数、两类基因的占比、前 20 个变体基因的匹配比对示例，以及所有全新基因的完整列表。
"""


import json
import os
import sys

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
output_report_path = os.environ.get(
    'RICEMIND_GENE_CLASSIFICATION_REPORT',
    str(RESULTS_DIR / 'gene_classification_report.txt'),
)

# 1. 获取所有出现在语料中的 Supplementary 基因 ID
print("正在读取已提取的样本文件...")
target_supp_ids = set()
with open(samples_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        target_id = data.get('validation_target_id')
        if target_id:
            target_supp_ids.add(target_id)

print(f"共找到 {len(target_supp_ids)} 个需要验证的 Supplementary 基因 ID。")

# 2. 从补充字典中获取这些 ID 对应的实际基因名称
print("正在映射 Supplementary 基因名称...")
supp_id_to_names = {}
with open(supp_dict_path, 'r', encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            gene_id = parts[2]
            gene_name = parts[3]
            if gene_id in target_supp_ids:
                if gene_id not in supp_id_to_names:
                    supp_id_to_names[gene_id] = set()
                supp_id_to_names[gene_id].add(gene_name)

# 3. 提取所有 Oryzabase 基因名称作为比对基准
print("正在加载 Oryzabase 基因名称库...")
oryza_names_lower = set()
with open(oryza_dict_path, 'r', encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            # 有时可能存在逗号分隔的多个名称，进行拆分处理
            names = [n.strip().lower() for n in parts[3].split(',')]
            for n in names:
                if len(n) >= 3: # 过滤掉过短的无意义名称
                    oryza_names_lower.add(n)

# 4. 开始分类比对
print("正在进行分类比对 (这可能需要十几秒钟)...")
category_variant = {} # 存储被判定为变体/家族的基因 {id: (supp_name, matched_oryza_name)}
category_novel = {}   # 存储被判定为全新的基因 {id: supp_name}

for supp_id, names in supp_id_to_names.items():
    is_variant = False
    matched_with = ""
    best_supp_name = list(names)[0] # 取其中一个名字作为代表
    
    for supp_name in names:
        supp_name_lower = supp_name.lower()
        if len(supp_name_lower) < 4:
            continue # 太短的名字直接跳过子串匹配，防止将 "Os1" 匹配给所有 "Os1x"
            
        for o_name in oryza_names_lower:
            # 互相检查是否互为子串
            if supp_name_lower in o_name or o_name in supp_name_lower:
                is_variant = True
                matched_with = o_name
                best_supp_name = supp_name
                break
        if is_variant:
            break
            
    if is_variant:
        category_variant[supp_id] = (best_supp_name, matched_with)
    else:
        category_novel[supp_id] = best_supp_name

# 5. 输出统计报告
total_classified = len(category_variant) + len(category_novel)
pct_variant = (len(category_variant) / total_classified) * 100 if total_classified > 0 else 0
pct_novel = (len(category_novel) / total_classified) * 100 if total_classified > 0 else 0

print("正在生成报告...")
report_lines = [
    "=== Supplementary Genes Classification Report ===",
    f"Total valid genes checked: {total_classified}",
    f"1. Variants / Family Names: {len(category_variant)} ({pct_variant:.2f}%)",
    f"2. Uncatalogued Novel Genes: {len(category_novel)} ({pct_novel:.2f}%)\n",
    "--- Top 20 Examples of Variants (Bridging the gap) ---"
]

# 变体部分依然保留前 20 个作为示例
for i, (supp_id, (s_name, o_name)) in enumerate(list(category_variant.items())[:20]):
    report_lines.append(f"[{supp_id}] {s_name}  ---> matched with Oryzabase: {o_name}")

# 新基因部分：输出全部！
report_lines.append("\n--- ALL Examples of Novel Genes (Overcoming database lag) ---")
for supp_id, s_name in category_novel.items():
    report_lines.append(f"[{supp_id}] {s_name}")

with open(output_report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report_lines))

print(f"\n分类完成！统计报告已生成: {output_report_path}")
print(f"变体/家族泛称: {pct_variant:.2f}%")
print(f"全新基因: {pct_novel:.2f}%")
