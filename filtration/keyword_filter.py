# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
# 执行阶段：当前配置下应在 annotations_statistics.py 之后运行。
# 输入是 ricemind_config.MULTI_ENTITY_OUTPUT（默认 multi_entity_sentences_1985-2025.jsonl），
# 不是 OGER 的年度输入 JSON；若要作为 OGER 前置筛选，必须先适配输入、输出和调用流程。
# 本仓库的 OGER 前置适配入口为 keyword_filter_pre_oger.py。
# 这个脚本是为了根据Notion里面的Prompt Design部分的生物事件相关的关键词筛选句子

'''
启动深度清洗脚本...
处理进度: 100000 | 保留: 13330 ...
处理进度: 200000 | 保留: 23209 ...
处理进度: 300000 | 保留: 32343 ...
处理进度: 400000 | 保留: 41915 ...
处理进度: 500000 | 保留: 51407 ...
处理进度: 600000 | 保留: 60444 ...
处理进度: 700000 | 保留: 69575 ...
处理进度: 800000 | 保留: 78510 ...
处理进度: 900000 | 保留: 87087 ...
处理进度: 1000000 | 保留: 95575 ...
处理进度: 1100000 | 保留: 103618 ...
处理进度: 1200000 | 保留: 111688 ...
处理进度: 1300000 | 保留: 119415 ...
处理进度: 1400000 | 保留: 126925 ...
处理进度: 1500000 | 保留: 134555 ...
处理进度: 1600000 | 保留: 142500 ...
处理进度: 1700000 | 保留: 150507 ...
处理进度: 1800000 | 保留: 158336 ...
处理进度: 1900000 | 保留: 166442 ...
处理进度: 2000000 | 保留: 174734 ...
处理进度: 2100000 | 保留: 182849 ...
处理进度: 2200000 | 保留: 190971 ...
处理进度: 2300000 | 保留: 199464 ...
处理进度: 2400000 | 保留: 208050 ...
--------------------------------------------------
处理完成！
原始输入: 2,476,650
最终保留: 213,802
保留率: 8.6%
--------------------------------------------------
统计详情:
  Drop_NoRice: 2,100,129
  Cat2_BioConcept: 128,242
  Drop_Blacklist: 77,303
  Cat4_Os: 70,192
  Drop_NoKeywords: 52,925
  Drop_RiceAsName: 31,495
  Cat3_Process: 15,323
  Cat5_LOC: 45

结果已保存至: keyword_filtered_rice_sentences.jsonl

'''





import json
import re
import os
import sys
from collections import defaultdict

# --- 配置输入输出 ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import KEYWORD_OUTPUT, MULTI_ENTITY_OUTPUT

INPUT_FILE = str(MULTI_ENTITY_OUTPUT)
OUTPUT_FILE = str(KEYWORD_OUTPUT)

# ==============================================================================
# 1. 定义关键词列表
# ==============================================================================


CAT1_REGEX = re.compile(r'\b(rice|oryza|sativa|indica|japonica|crop)\b', re.IGNORECASE)

# Category 2: Bio Concepts (列表)
CAT2_KEYWORDS = [
    'gene', 'protein', 'mutation', 'mutant', 'snp', 'cnv', 'sv', 'variant', 'allele', 
    'genotype', 'genetic', 'insert', 'indel', 'deletion', 'inversion', 
    'duplication', 'missense', 'nonsense', 'silent', 'frameshift', 
    'synonymous', 'homozygous', 'heterozygous', 'locus', 'loci', 'exon', 
    'intron', 'promoter', 'enhancer', 'utr', 'cds', 'silencer', 'trait', 
    'phenotype', 'stress', 'resistance', 'tolerant', 'tolerance', 
    'variety', 'varieties', 'metabol', 'qtl', 'transgenic', 'genome', 'breeding'
]

# Category 3: Bio Processes (全词匹配 \bword\b，不区分大小写)
# 直接使用你提供的列表，Python 会自动处理其中的特殊符号（如-induced）
CAT3_RAW_LIST = [
    'accelerate', 'accelerated', 'accelerates', 'activate', 'activated', 'activates', 'allowed', 'allows', 
    'augment', 'augmentation', 'augmented', 'augments', 'coactivator', 'costimulate', 'elevate', 'elevated', 
    'elevates', 'elicit', 'elicited', 'elicits', 'enable', 'enables', 'enhance', 'enhanced', 'enhancement', 
    'enhancer', 'enhances', 'enhancing', 'exacerbate', 'exacerbated', 'exacerbates', 'expedited', 'facilitate', 
    'facilitated', 'facilitates', 'improve', 'improved', 'improvement', 'improves', 'induce', 'induced', 
    '-induced', 'induces', 'potentiate', 'potentiated', 'potentiates', 'promote', 'promoted', 'promoter', 
    'promotes', 'reactivate', 'reactivated', 'reactivation', 'restore', 'restored', 'restores', 'stabilize', 
    'stabilized', 'stimulate', 'stimulated', 'stimulates', 'strengthened', 'strengthening', 'strengthens', 
    'transactivated', 'transactivating', 'transactivation', 'upregulate', 'upregulated', 'upregulates', 
    'ablated', 'abolish', 'abolished', 'abolishes', 'abolishing', 'abrogate', 'abrogated', 'abrogates', 
    'antagonized', 'antagonizes', 'antagonize', 'coactivated', 'coinhibition', 'compete', 'competes', 
    'counteract', 'counteracted', 'counteracting', 'counteracts', 'deactivated', 'deactivates', 'degrade', 
    'degraded', 'degrader', 'depressed', 'destabilize', 'destabilized', 'destroyed', 'destroying', 'diminish', 
    'diminished', 'diminishes', 'diminishing', 'disassembled', 'disassembles', 'displace', 'displaced', 
    'displacement', 'displaces', 'disrupt', 'disrupting', 'disruption', 'dissociate', 'dissociated', 
    'disturb', 'disturbances', 'disturbed', 'disturbing', 'disturbs', 'divert', 'downregulate', 'down-regulate', 
    'eliminate', 'eliminated', 'eliminates', 'hinder', 'hindered', 'hindering', 'hinders', 'impair', 'impaired', 
    'impairing', 'impairment', 'impairs', 'impede', 'impeded', 'impedes', 'inactivate', 'inactivated', 'inhibit', 
    'inhibited', 'inhibiting', 'inhibition', 'inhibitions', 'inhibitive', 'inhibitory', 'inhibits', 'interceptor', 
    'interfere', 'interfered', 'interference', 'interferes', 'interfering', 'interrupt', 'interrupted', 
    'interrupting', 'interruption', 'interrupts', 'negated', 'negates', 'neutralize', 'neutralized', 'neutralizes', 
    'nullify', 'obliterated', 'obstructive', 'oppose', 'opposed', 'opposes', 'outcompeted', 'perturbation', 
    'perturbed', 'prevent', 'prevented', 'preventing', 'prevention', 'prevents', 'prohibited', 'prohibiting', 
    'reduce', 'reduced', 'reduces', 'reducing', 'repress', 'repressed', 'represses', 'repressing', 'repressive', 
    'restrict', 'restricting', 'restricts', 'revert', 'reverted', 'reverting', 'suppress', 'suppressed', 
    'suppresses', 'suppressing', 'suppression', 'suppressive', 'terminated', 'terminates', 'transrepresses', 
    'transrepression', 'undermined', 'unstimulated', 'weaken', 'weakened', 'weakening', 'weakens', 'abolished', 
    'abrogated', 'absence', 'antibody', 'blockage', 'blocked', 'blocking', 'decrease', 'decreased', 'decreasing', 
    'deficiency', 'deficient', 'deleted', 'deleting', 'deletion', 'depleted', 'depleting', 'depletion', 
    'diminished', 'disruption', 'downregulate', 'down-regulate', 'downregulated', 'down-regulated', 'downregulates', 
    'downregulating', 'down-regulating', 'downregulation', 'down-regulation', 'eliminated', 'impaired', 'inhibit', 
    'inhibited', 'inhibiting', 'inhibition', 'inhibitor', 'inhibitors', 'inhibitory', 'inhibits', 'interfere', 
    'interference', 'interfering', 'knock', 'knockdown', 'knock-down', 'knocked', 'knocking', 'knockout', 
    'knock-out', 'loss', 'neutralizing', 'prevent', 'prevented', 'reduce', 'reduced', 'reduces', 'reducing', 
    'rnai', 'sirna', 'suppressed', 'suppresses', 'suppressing', 'suppression'
]

# 去重并构建正则
# 使用 re.escape 确保特殊字符（如 -induced）被正确处理
# \b 表示单词边界
cat3_pattern_str = r'\b(?:' + '|'.join(map(re.escape, list(set(CAT3_RAW_LIST)))) + r')\b'
CAT3_REGEX = re.compile(cat3_pattern_str, re.IGNORECASE)

# Category 4: OS 开头的单词 (正则: \bOs\w*)
# 匹配单词边界后紧跟 Os，后面跟任意字母数字
CAT4_REGEX = re.compile(r'\bos\w*', re.IGNORECASE)

# Category 5: LOC+数字 开头的单词 (正则: \bLOC\d+)
# 匹配单词边界后紧跟 LOC，然后至少一个数字
CAT5_REGEX = re.compile(r'\bloc\d+\w*', re.IGNORECASE)


# ==============================================================================
# 2. 新增：黑名单逻辑 (The Cleaner)
# ==============================================================================

# 绝对排除词 (一旦出现，直接丢弃)
BLACKLIST_TERMS = [
    'cholera', 'stool', 'diarrhea', 'patient', 'hospital', 'clinical', 'syndrome', # 医学霍乱
    'yeast', 'saccharomyces', 'cerevisiae', 'candida', # 酵母误报
    'human', 'women', 'men', 'child', 'infant', # 人类研究
    'rat', 'mouse', 'mice', 'hamster', 'rabbit', # 动物模型 (除非是转基因验证，但通常噪音大)
    'salary', 'income', 'currency', 'market price', 'discount rate', 'earnings', # 经济学
    'recipe', 'cooking', 'fried rice', 'noodle', # 食品加工
    'rice university', 'rice k.c.', 'rice, k', 'rice j', 'rice et al' # 人名/机构名
]

# 【关键修复】: 编译黑名单正则
BLACKLIST_REGEX = re.compile(r'\b(?:' + '|'.join(map(re.escape, BLACKLIST_TERMS)) + r')\b', re.IGNORECASE)

# 【关键修复】: 编译人名正则
RICE_NAME_REGEX = re.compile(r'\brice\s*(?:,|et al|[A-Z]\.)', re.IGNORECASE)

# ==============================================================================
# 3. 筛选逻辑函数
# ==============================================================================

def is_valid_sentence(text):
    text_lower = text.lower()
    
    # --- Step 1: 负面清单清洗 ---
    if BLACKLIST_REGEX.search(text):
        return False, "Blacklist"
    
    if RICE_NAME_REGEX.search(text):
        return False, "RiceAsName"

    # --- Step 2: 必须包含 Rice ---
    if not CAT1_REGEX.search(text):
        return False, "NoRice"

    # --- Step 3: 正面关键词检查 ---
    
    # 优先检查最准确的基因编号
    if CAT4_REGEX.search(text): return True, "Cat4_Os"
    if CAT5_REGEX.search(text): return True, "Cat5_LOC"
    
    # 检查生物概念
    if any(k in text_lower for k in CAT2_KEYWORDS): return True, "Cat2_BioConcept"
        
    # 检查生物过程
    if CAT3_REGEX.search(text): return True, "Cat3_Process"
        
    return False, "NoKeywords"

# ==============================================================================
# 4. 主程序
# ==============================================================================

def run_refined_filter():
    print(f"启动深度清洗脚本...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 文件 {INPUT_FILE} 不存在")
        return

    stats = defaultdict(int)
    total = 0
    saved = 0
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_FILE, 'w', encoding='utf-8') as fout:
        
        for line in fin:
            total += 1
            if total % 100000 == 0:
                print(f"处理进度: {total} | 保留: {saved} ...")
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue # 跳过损坏的行
            
            text = data.get('text', '')
            
            if len(text) < 20 or len(text) > 2000:
                continue

            # 【关键修改】这里不再使用 broad exception，如果报错直接让它崩，方便调试
            valid, tag = is_valid_sentence(text)
            
            if valid:
                data['filter_tag'] = tag
                fout.write(json.dumps(data, ensure_ascii=False) + '\n')
                saved += 1
                stats[tag] += 1
            else:
                stats[f"Drop_{tag}"] += 1

    print("-" * 50)
    print(f"处理完成！")
    print(f"原始输入: {total:,}")
    print(f"最终保留: {saved:,}")
    if total > 0:
        print(f"保留率: {saved/total:.1%}")
    print("-" * 50)
    print("统计详情:")
    for k, v in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {k}: {v:,}")
    
    print(f"\n结果已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_refined_filter()
