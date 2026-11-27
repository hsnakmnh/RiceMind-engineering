> 2026-11-27 完整资源版：新部署先看 [资源版指南](BUNDLED_WORKFLOW.md)。词典、映射、参考快照与句子处理入口已集中；本文保留详细参数和历史服务器说明。旧的重新下载词典、手建平铺词典链接步骤在新包中可跳过。

# RiceMind 项目使用手册

版本：2026-10-29；2026-11-27发布副本通用化路径。适用于当前工程适配版，以及服务器 `/path/to/RiceMind-engineering` 的规范目录布局。

**发布副本说明：** 历史批次数据未附仓库；/path/to/均需替换，活动配置从示例创建。来源/许可见ATTRIBUTION.md。

本文按当前本地源码、原有流程文档和用户提供的服务器成功日志整理。服务器与本地并未完全同步；参数以实际上传的脚本为准。本文编写期间没有重新运行服务器数据处理。

**当前 2025—2026 批次已完成到公共库比较、差集及句子证据导出。已有结果的使用者先读第 1、15、16 节；第 6—14 节供新部署或新批次运行。历史计数不能用作其他数据集的强制验收值。**

## 目录

1. [当前完成情况与最终文件](#current)
2. [整体流程与入口](#workflow)
3. [目录和资源准备](#layout)
4. [软件环境和模型](#environment)
5. [一次配置与路径优先级](#configuration)
6. [PubTator 转句子](#prepare)
7. [前置筛句与年度拆分](#filter)
8. [OGER 五轮标注](#oger)
9. [SciSpacy 和 PhraseMatcher](#other-annotation)
10. [分类黑名单清理](#clean)
11. [三工具统计](#statistics)
12. [参考资料、组学 JSON 与基因主表](#reference)
13. [文献关联构建与核查](#associations)
14. [公共库比较与差集导出](#coverage)
15. [结果核验和交付](#delivery)
16. [修改后从哪一步重跑](#rerun)
17. [项目全部业务脚本索引](#scripts)
18. [常见问题](#troubleshooting)
19. [复现边界与核对来源](#scope)

<a id="current"></a>
## 1. 当前完成情况与最终文件

### 1.1 已完成的主流程

| 阶段 | 完成依据与本批次记录 |
|---|---|
| 文献转句子 | 2025 年 807,372 条，2026 年 400,517 条，合计 1,207,889 条 |
| 前置筛句 | 保留 35,451 条；2025 年 24,189 条，2026 年 11,262 条 |
| 三类工具标注 | OGER 五轮、SciSpacy 五类、PhraseMatcher 五类均有成功日志；OGER 包含两套基因词典 |
| 清理与统计 | 已生成 cleaned 和统计 JSONL；关联构建还会应用当前分类黑名单 |
| 基因主表 | 49,345 条参考记录，同时生成多候选编号索引 |
| 文献关联 | GTA 136,632 行，GVA 3,912 行，TVA 10,226 行 |
| 核查材料 | 结构检查通过；映射待审提及 60 条、涉及 11 个 ID；三类关联各抽样 50 行 |
| 公共对照库 | 已使用作者 Zenodo 成品并校验；没有本地重新整合四来源公共资料 |
| 比较及差集证据 | RAP 关联 53,107 对，共有 2,038 对、NLP 差集 51,069 对；差集句子证据 88,807 行 |

人工专家审定未确认为全部完成；当前结果应称为工程适配批次。可选专项分析未全部纳入此主流程。

### 1.2 当前已确认的批次路径

以下命令仅设置变量，不执行处理：

```bash
cd /path/to/RiceMind-engineering
OGER_RUN_DIR="$PWD/results/oger/five_passes/20260921_162731_27405"
CLEANED_DIR="$PWD/results/cleaned/keyword_filtered"
STAT_DIR="$PWD/results/statistics/keyword_filtered/20260929_165826_18558"
ASSOC_DIR="$PWD/results/associations/keyword_filtered/20261014_095526_184013_31655"
COVERAGE_DIR="$PWD/results/coverage/20261016_110551_638065_22509"
PUBLIC_FILE="$PWD/sequence_data/reference/public_gta/zenodo_19702501/Unified_Rice_GTA_Database.tsv"
```

新运行应记录程序打印的 `[OUTPUT]`，再更新这些变量。不要直接选“最新目录”，因为它可能属于 dry-run 或失败批次。

### 1.3 最终交付文件

| 位于关联批次中的文件 | 含义 | 当前记录 |
|---|---|---|
| `NLP_Rice_GTA_Database.tsv` | **主要结果表**：逐句基因—性状/功能共现候选及原句证据 | 136,632 行，约 74 MB |
| `NLP_Rice_GVA_TVA_Database.tsv` | 基因—品种、性状—品种，按 `Relation_Type` 区分 | 14,138 行，约 7.1 MB |
| `NLP_Rice_GTA_Trend.tsv` | 按 `Gene_Key + Ontology_ID` 聚合，统计文献和年份 | 78,868 对，约 15 MB |
| `normalized_sentences.jsonl` | 全体句子、规范化实体、排除记录和映射状态 | 35,451 条句子 |
| `gene_normalization_audit.tsv` | 逐基因提及的编号映射和规则处理 | 供追溯 |
| `association_summary.json` | 计数、来源、输入输出哈希 | 供核验 |
| `coverage_details/gta_pairs_nlp_only.tsv` | 公共快照未收录的精确 RAP—本体组合 | 51,069 对 |
| `coverage_details/gta_pairs_nlp_only_sentence_evidence.tsv` | 上述差集的原句、PMID 和映射字段 | 88,807 行，约 48 MB |
| `coverage_details/coverage_details_manifest.json` | 差集计数、比较规则和输入哈希 | 供核验 |

关联主表生成于 10 月 14 日，差集证据生成于 10 月 19 日，以用户提供的服务器记录为依据。Trend 为聚合表，主要结果表保存逐句证据，建议一起交付。

<a id="workflow"></a>
## 2. 整体流程与入口

```text
上游文献收集 → 文献级 PubTator
  ↓
pubtator_to_sentence_tsv.py → 年度句子 TSV
  ↓
keyword_filter_pre_oger.py → 合并 TSV / OGER JSON / 年份映射
  ├─ 合并 JSON → run_oger_five_passes.sh → OGER 五轮
  └─ 按年份拆分 TSV → SciSpacy 五类 + PhraseMatcher 五类
                         ↓ 三套工具完成后合流
remove_noise.py → 清理后的标注副本
  ↓
annotations_statistics.py → 全句子标注 JSONL
  ↓                                参考分支：下载资料 → 组学 JSON → 基因主表
build_nlp_associations.py ← 基因主表和候选索引
  ├─ GTA / GVA / TVA / Trend
  ├─ prepare_association_review.py → 核查材料
  └─ compare_gta_coverage.py ← 作者公共 GTA 成品库
       ↓
export_coverage_details.py → 交并集清单和差集句子证据
```

之前的 `Esearch_get_PMID_PMCID.py` 和 `Alterome-pipeline.sh` 属于项目外的上游流程。RiceMind 当前仓库未包含这套文献获取入口，执行 `prepare` 不会自动访问 PubMed 重收文献。

| shell 命令 | 实际代码 | 当前用途 |
|---|---|---|
| `bash run_ricemind.sh config` | `ricemind_config.py` | 打印路径 |
| `bash run_ricemind.sh prepare` | `annotation/pubtator_to_sentence_tsv.py` | 主流程 |
| `bash run_ricemind.sh keyword-filter-pre-oger` | `filtration/keyword_filter_pre_oger.py` | 主流程 |
| `bash run_oger_five_passes.sh --input-file ...` | 每轮调用 `annotation/call_oger.py` | **当前 OGER 入口** |
| `bash run_ricemind.sh scispacy` | 五个 `scispacy_match_*.py` | 主流程 |
| `bash run_ricemind.sh phrase` | `annotation/single_dictionary_match_multi_process.py` | 主流程，显式指定词典目录 |
| `bash run_ricemind.sh remove-noise` | `filtration/remove_noise.py` | 主流程 |
| `bash run_ricemind.sh annotations-statistics` | `filtration/annotations_statistics.py` | 主流程 |
| `bash run_ricemind.sh oger-input` | `annotation/tsv_2_txt_json.py` | 旧年度转换；前置筛选已生成 JSON 时可跳过 |
| `bash run_ricemind.sh oger` | 旧单词典年度入口 | 当前五轮流程不使用 |
| `bash run_ricemind.sh basic` | prepare + 旧年度 JSON 转换 | 仅前处理，不包含筛句或标注 |

后半程的组学、主表、关联、比较和导出尚未全部封装在统一 shell 入口中，应使用本文对应的 Python 命令。

**复制运行约定：** 每次新终端先激活环境、进入项目根目录；直接执行 Python 前加载环境文件。示例中的 shell 变量仅在当前终端保留。各步骤完成并通过检查后再进入下步，`nohup ... &` 只表示已经启动。复制代码时不要复制终端提示符、`>` 提示或 Markdown 围栏；多行反斜杠后不加空格。包含历史 run ID 的示例用于已有批次，新批次应替换为实际输出路径。

<a id="layout"></a>
## 3. 目录和资源准备

沿用服务器已整理的结构，无需为本手册再次迁移数据：

```text
RiceMind/
├── annotation/、filtration/、build_dataset/、build_GTA/、analyse/  业务代码
├── configs/                         可选的批次环境配置
├── docs/                            本手册和示例
├── ricemind_env.sh                  本机实际路径
├── ricemind_config.py               Python 配置解析与默认值
├── run_ricemind.sh、run_oger_five_passes.sh
├── RICE-pubtator-dir/               上游文献文件
├── rice_sentences/                  关键词筛选前的年度句子
├── dict-dir/
│   ├── annotation/                  五份三列词典
│   ├── oger/genes/                  两份 OGER 基因词典
│   ├── oger/ontology/               五份 OGER 非基因词典
│   ├── filtering/blacklists/        六类清理规则
│   ├── views/oger_flat/             可选的平铺软链接视图
│   └── archive/                     原始词典包和历史版
├── asset/protein_gene_mapping.txt
├── sequence_data/
│   ├── reference/                   官方序列和 Oryzabase 快照、manifest
│   │   └── public_gta/zenodo_19702501/
│   └── rice_multi_omics.json 及构建报告
├── standard_gene/                  基因主表、候选索引、报告
├── results/                        阶段/批次输出
├── logs/                           后台及环境日志
├── third_party/                    可选的模型安装包等
└── tests/                          工程验证
```

### 3.1 资源清单

| 资源 | 来源和位置 | 使用阶段 |
|---|---|---|
| 文献级 PubTator | 上游交付 `RICE-pubtator-dir/*.pmid-pmcid.txt` | prepare |
| 七份 OGER 词典 | 作者 GitHub `annotation/dict.tar.gz`，存入规范 `oger/` 子目录 | OGER、统计标准名 |
| 五份 `{co,go,to,rto,variety}-dict.tsv` | 作者三列词典，本服务器来自 `dict.rar` | SciSpacy、PhraseMatcher |
| 六类 `*_blacklist.tsv` | `dict-dir/filtering/blacklists/` | 清理、关联构建 |
| `en_core_sci_scibert-0.5.4.tar.gz` | 官方模型，安装后配置真实数据目录 | SciSpacy |
| Oryzabase、GFF3、DNA、cDNA、pep | `sequence_data/reference/` | 组学和主表 |
| 蛋白/转录本编号映射 | `asset/protein_gene_mapping.txt` | 主表 |
| 公共 GTA 成品 | 作者 Zenodo 19702501 | 比较 |

OGER 多列词典和三列词典不能仅重命名后互相替代。`gene_list/` 单列名单也不能替代完整编号映射。

### 3.2 格式约定

- PubTator：文献文本中含 `PMID|t|标题`、`PMID|a|文本` 等记录；上游决定实际正文范围。
- 句子 TSV：UTF-8、无表头、每行 `PMID<TAB>Sentence_ID<TAB>Sentence_Text`。正文不得自行加 Tab/换行。
- OGER JSON：一个数组，元素为 `{"id": "句子ID", "text": "正文"}`；不是逐行 JSONL。
- 年份映射：带表头的 `Sentence_ID<TAB>Year`。
- SciSpacy/PhraseMatcher：带表头的八列 TSV，见下文。
- 统计/规范化 JSONL：每行一个句子对象，逐行 `json.loads`。

```text
PMID  Sentence_ID  Trait_ID  Standard_Name  Start  End  Matched_Text  Sentence_Text
```

当前八列输出中的坐标为 0 起始、右端不包含的字符区间，应满足 `Sentence_Text[Start:End] == Matched_Text`。原作者另给的 PhraseMatcher 脚本使用 token 位置和不同列顺序，不能直接混用。

文件名 `rice_sentences/2025_filtered_sent.txt` 中的 `filtered` 沿用历史命名，不能据此认定已经完成关键词筛选。

### 3.3 新部署时准备词典

服务器现有词典齐全时跳过。作者 OGER 包可从 [RiceMind 的 dict.tar.gz](https://github.com/muhaha2/RiceMind/blob/main/annotation/dict.tar.gz) 获取，下载到 `dict-dir/archive/dict.tar.gz`。五份三列词典使用作者提供的 `dict.rar`，放入同一 archive 目录；安装 OGER 软件本身不会自动生成这些专用词典。

以下新部署示例保留原始包，活动文件已存在时不覆盖：

```bash
(
set -e
mkdir -p dict-dir/oger/genes dict-dir/oger/ontology
gzip -t dict-dir/archive/dict.tar.gz
for name in oryzabase_gene supplementary_gene; do
    target="dict-dir/oger/genes/${name}_oger_dict.tsv"
    if [[ ! -e "$target" ]]; then
        tar -xOf dict-dir/archive/dict.tar.gz "dict/${name}_oger_dict.tsv" > "$target"
    fi
    test -s "$target"
done
for name in co go to rto variety; do
    target="dict-dir/oger/ontology/${name}_oger_dict.tsv"
    if [[ ! -e "$target" ]]; then
        tar -xOf dict-dir/archive/dict.tar.gz "dict/${name}_oger_dict.tsv" > "$target"
    fi
    test -s "$target"
done
)
```

三列词典的原始 RAR 内含 `dict/` 子目录，服务器已有 `unrar` 时：

```bash
(
set -e
unrar t dict-dir/archive/dict.rar
mkdir -p dict-dir/archive/scispacy_original dict-dir/annotation
unrar x -o- dict-dir/archive/dict.rar dict-dir/archive/scispacy_original/
for name in co go to rto variety; do
    source_file="dict-dir/archive/scispacy_original/dict/$name-dict.tsv"
    test -s "$source_file"
    cp -n "$source_file" "dict-dir/annotation/$name-dict.tsv"
done
)
```

本次活动 `variety-dict.tsv` 与原件的差异只有去掉首行 `variety_ID / variety_name / synonyms` 表头，其余词条相同。当前 SciSpacy 读取器不显式跳过该表头；新部署可在活动拷贝中仅去除明确识别的表头，原件留在 archive：

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("dict-dir/annotation/variety-dict.tsv")
raw = p.read_bytes()
first, separator, remainder = raw.partition(b"\n")
fields = first.decode("utf-8-sig").rstrip("\r").split("\t")
if len(fields) >= 2 and fields[0] == "variety_ID" and fields[1] == "variety_name":
    assert separator, "表头后没有数据"
    p.write_bytes(remainder)
    print("仅移除已识别的表头，原始包保留")
else:
    print("无此表头，保留原文件")
PY
```

不要把这一操作用于 OGER 多列词典。OGER 调用本身已有 `termlist_skip_header true` 设置，应保留作者包的原始表头/列格式，避免将三个列格式混淆。源码数据未齐全、包成员名与此处不同或字段不符时先核对来源，不强行套用提取命令。

<a id="environment"></a>
## 4. 软件环境和模型

### 4.1 现有环境

本批次服务器使用 `ad_alterome`，安装日志中 Python 为 3.8、OGER 为 1.5、SciSpacy 及模型为 0.5.4。新适配的参考/主表/关联等脚本以 Python 3.8+ 标准库为主。服务器尚未提供完整依赖 lock，因此下面几项版本不等于完整环境锁定。

```bash
conda activate ad_alterome
cd /path/to/RiceMind-engineering
python3 --version
python3 -m pip --version
mkdir -p logs/environment
python3 -m pip freeze > logs/environment/pip-freeze.txt
conda env export --no-builds > logs/environment/conda-environment.yml
```

现有环境可用时先保存记录，无需重装。新环境安装入口如下；安装成功和依赖兼容性仍需实际验证：

```bash
python3 -m pip install \
  "git+https://github.com/OntoGene/OGER.git@f23cf9bec70ba51f85605f26f3de2df72f7c4d5a"
python3 -m pip install "scispacy==0.5.4"
python3 -m pip install pandas matplotlib matplotlib-venn tqdm
```

OGER 提交号来自本次安装日志。SciSpacy 0.5.4 声明 `spacy>=3.7.0,<3.8.0`，库和模型需分别安装并匹配版本，依据 [0.5.4 安装声明](https://github.com/allenai/scispacy/blob/v0.5.4/setup.py) 和 [官方模型说明](https://github.com/allenai/scispacy/blob/v0.5.4/README.md)。

### 4.2 安装模型并查真实路径

电脑下载并上传 [官方 SciBERT 0.5.4 模型包](https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_scibert-0.5.4.tar.gz) 后：

```bash
python3 -m pip install ./en_core_sci_scibert-0.5.4.tar.gz
python3 -m pip check
python3 - <<'PY'
from pathlib import Path
import oger
import en_core_sci_scibert
print("OGER 包目录:", Path(oger.__file__).resolve().parent)
root = Path(en_core_sci_scibert.__file__).resolve().parent
for cfg in sorted(root.rglob("config.cfg")):
    print("SciSpacy 模型数据目录:", cfg.parent)
PY
```

必须配置到直接包含 `config.cfg` 的数据目录，而非外层模型 Python 包目录。服务器当前示例为：

```text
/path/to/python-env/site-packages/en_core_sci_scibert/en_core_sci_scibert-0.5.4
```

仅在相关依赖已经齐全、核对兼容性后才考虑 `--no-deps`。曾经的 transformer factory 错误涉及组件依赖，不能单靠停用组件解决。

第 5 节配置后检查：

```bash
source ricemind_env.sh
python3 - <<'PY'
import os
from pathlib import Path
import spacy
from oger.ctrl.run import run
from oger.ctrl import parameters
p = Path(os.environ["RICEMIND_SCISPACY_MODEL"])
assert (p / "config.cfg").is_file(), p
nlp = spacy.load(str(p), disable=[
    "ner", "parser", "tagger", "lemmatizer", "transformer", "attribute_ruler"
])
print("OGER 导入和 SciSpacy 模型加载通过")
PY
```

`disable` 会停止组件执行，但组件仍可能被加载；依赖缺失时检查模型和 `spacy-transformers`，不要未经确认替换分词模型。[spaCy 加载说明](https://spacy.io/api/language)

<a id="configuration"></a>
## 5. 一次配置与路径优先级

### 5.1 配置分工和需要修改的内容

`ricemind_env.sh` 保存本机实际路径；`ricemind_config.py` 供 Python 解析环境变量和提供默认值。两个包装脚本自动加载环境文件；直接执行 Python 前要在同一终端 `source ricemind_env.sh`。

已有服务器配置可继续使用。新机器按实际位置配置以下关键字段，模型和 OGER 包位置用第 4 节查询结果：

```bash
export RICEMIND_BASE_DIR="/path/to/RiceMind-engineering"
export RICEMIND_PUBTATOR_DIR="$RICEMIND_BASE_DIR/RICE-pubtator-dir"
export RICEMIND_SENTENCE_DIR="$RICEMIND_BASE_DIR/rice_sentences"
export RICEMIND_RESULTS_DIR="$RICEMIND_BASE_DIR/results"
export RICEMIND_OGER_INPUT_DIR="$RICEMIND_RESULTS_DIR/oger_input"
export RICEMIND_OGER_OUTPUT_DIR="$RICEMIND_RESULTS_DIR/oger"
export RICEMIND_SCISPACY_OUTPUT_ROOT="$RICEMIND_RESULTS_DIR/scispacy"
export RICEMIND_PHRASE_OUTPUT_ROOT="$RICEMIND_RESULTS_DIR/phrase"

export RICEMIND_DICT_DIR="$RICEMIND_BASE_DIR/dict-dir"
export RICEMIND_ANNOTATION_DICT_DIR="$RICEMIND_DICT_DIR/annotation"
export RICEMIND_CO_DICT="$RICEMIND_ANNOTATION_DICT_DIR/co-dict.tsv"
export RICEMIND_GO_DICT="$RICEMIND_ANNOTATION_DICT_DIR/go-dict.tsv"
export RICEMIND_TO_DICT="$RICEMIND_ANNOTATION_DICT_DIR/to-dict.tsv"
export RICEMIND_RTO_DICT="$RICEMIND_ANNOTATION_DICT_DIR/rto-dict.tsv"
export RICEMIND_VARIETY_DICT="$RICEMIND_ANNOTATION_DICT_DIR/variety-dict.tsv"
export RICEMIND_OGER_DICT_DIR="$RICEMIND_DICT_DIR/oger"
export RICEMIND_OGER_GENE_DIR="$RICEMIND_OGER_DICT_DIR/genes"
export RICEMIND_OGER_ONTOLOGY_DIR="$RICEMIND_OGER_DICT_DIR/ontology"
export RICEMIND_OGER_DICT_ARCHIVE="$RICEMIND_DICT_DIR/archive/dict.tar.gz"
export RICEMIND_NOISE_BLACKLIST_DIR="$RICEMIND_DICT_DIR/filtering/blacklists"

export RICEMIND_STANDARD_GENE_DIR="$RICEMIND_BASE_DIR/standard_gene"
export RICEMIND_SEQUENCE_DATA_DIR="$RICEMIND_BASE_DIR/sequence_data"
export RICEMIND_SCISPACY_MODEL="/path/to/python-env/site-packages/en_core_sci_scibert/en_core_sci_scibert-0.5.4"
export RICEMIND_OGER_PACKAGE="/path/to/python-env/site-packages/oger"
```

五个词典实际变量为 `RICEMIND_CO_DICT` 等；打印的 `DICT_CO` 是显示标签，不能据此写成 `RICEMIND_DICT_CO`。根目录实际读取 `RICEMIND_DICT_DIR`，而不是任意新造的变量名。

源码仍留有 `OGER++/riceMind_dicts` 等兼容默认值；有效环境配置会覆盖它们。机器迁移主要改路径配置和运行参数，无需逐个改业务代码。

### 5.2 避免包装脚本覆盖临时环境变量

当前基础环境对路径使用无条件 `export`；在命令前临时设 `RICEMIND_SENTENCE_DIR=... bash run_ricemind.sh ...`，可能被脚本随后重新 source 的基础配置覆盖。

使用本手册附带的批次示例：

```bash
mkdir -p configs
cp -n docs/examples/ricemind_keyword_filtered.env.sh.example \
  configs/keyword_filtered.env.sh
RICEMIND_ENV_FILE="$PWD/configs/keyword_filtered.env.sh" \
  bash run_ricemind.sh config
```

示例必须复制到 `<项目>/configs/` 后再用。它先读取基础配置，再将输入/输出改为筛选后分支，并取消旧单文件黑名单变量。预期输出：

```text
SENTENCE_DIR=.../results/sentence_keyword_filtered
SCISPACY_OUTPUT_ROOT=.../results/scispacy/keyword_filtered
PHRASE_OUTPUT_ROOT=.../results/phrase/keyword_filtered
OGER_DICT_DIR=.../dict-dir/oger
DICT_CO=.../dict-dir/annotation/co-dict.tsv
```

此配置供筛选后的标注使用；最初 prepare 使用基础配置和原始句子输出。新批次可另复制一份，修改输出路径以隔离成果。

### 5.3 统计读取器的平铺词典视图

当前本地 `annotations_statistics.py` 的标准名读取器要求同目录下有七个平铺文件。服务器的 `genes/ontology/` 规范布局可通过软链接视图兼容，不需要复制或移动活动词典：

```bash
export OGER_STATS_DICT_DIR="$PWD/dict-dir/views/oger_flat"
(
set -e
source ricemind_env.sh
mkdir -p "$OGER_STATS_DICT_DIR"
for source_file in \
  "$RICEMIND_OGER_GENE_DIR/oryzabase_gene_oger_dict.tsv" \
  "$RICEMIND_OGER_GENE_DIR/supplementary_gene_oger_dict.tsv" \
  "$RICEMIND_OGER_ONTOLOGY_DIR/co_oger_dict.tsv" \
  "$RICEMIND_OGER_ONTOLOGY_DIR/go_oger_dict.tsv" \
  "$RICEMIND_OGER_ONTOLOGY_DIR/to_oger_dict.tsv" \
  "$RICEMIND_OGER_ONTOLOGY_DIR/rto_oger_dict.tsv" \
  "$RICEMIND_OGER_ONTOLOGY_DIR/variety_oger_dict.tsv"
do
    test -s "$source_file"
    link_path="$OGER_STATS_DICT_DIR/$(basename "$source_file")"
    if [[ -e "$link_path" || -L "$link_path" ]]; then
        test "$(readlink -f "$link_path")" = "$(readlink -f "$source_file")"
    else
        ln -s "$source_file" "$link_path"
    fi
done
)
```

第 11 节统计显式传该目录。若服务器新版已经支持规范双层目录，可按其实际参数使用；本文采用兼容视图避免依赖未同步版本。源词典再次移动时要更新链接；保留内容哈希才能追溯旧结果。

<a id="prepare"></a>
## 6. PubTator 转句子

**代码：** `annotation/pubtator_to_sentence_tsv.py`，为后期补充适配器。读取文献文本、清理 HTML/空白、按 PMID 合并去重并分句，默认不输出文章标题。

**需要变更：** 基础配置的输入/输出目录；文件名不符合后缀时用 `--pattern`。默认匹配 `*.pmid-pmcid.txt`，例如 `Rice.2025.pmid-pmcid.txt`。

```bash
cd /path/to/RiceMind-engineering
bash run_ricemind.sh prepare \
  --input-dir "$PWD/RICE-pubtator-dir" \
  --output-dir "$PWD/rice_sentences"
```

输出 `2025_filtered_sent.txt`、`2026_filtered_sent.txt` 等年度三列 TSV。同目录重跑会写回同名文件；已用于标注的句子应保留，重算另设 `--output-dir`。

```bash
wc -l rice_sentences/*_filtered_sent.txt
head -n 3 rice_sentences/2025_filtered_sent.txt
```

**完成标志：** 日志出现“RiceMind 句子文件已生成”及各年度文章/句子计数。此时还没有关键词筛选。

`--exclude-title` 为默认行为的兼容参数；需要标题时才使用 `--include-title`。严格日期过滤需要实际 PMID 日期表：

```bash
bash run_ricemind.sh prepare \
  --input-dir "$PWD/RICE-pubtator-dir" \
  --output-dir "$PWD/rice_sentences_by_date" \
  --date-map "$PWD/pmid_date.tsv" \
  --start-date 2025-03-01 --end-date 2026-09-30
```

日期表为 `PMID<TAB>YYYY-MM-DD`。没有日期表时，年度标签来自上游文件，不能仅凭文件名证明发表月份。当前任务已接受按 2025/2026 年度数据集统计，不必补做月份筛选。

<a id="filter"></a>
## 7. 前置筛句与年度拆分

### 7.1 筛句、合并并生成 OGER JSON

**代码：** `filtration/keyword_filter_pre_oger.py`，内部导入 `keyword_filter.py` 的 `is_valid_sentence`。

**需要变更：** 年份、原始年度句子目录、独立输出目录和标签。修改关键词或句长条件属于方法变更，应另记录规则版本。

```bash
bash run_ricemind.sh keyword-filter-pre-oger \
  --start-year 2025 --end-year 2026 \
  --input-dir "$PWD/rice_sentences" \
  --output-dir "$PWD/results/oger_input/keyword_filtered" \
  --dataset-label 2025-2026_keyword
```

输出：

```text
results/oger_input/keyword_filtered/
├── 2025-2026_keyword_filtered_sent.tsv
├── 2025-2026_keyword_filtered_sent.json
├── 2025-2026_keyword_sentence_year_map.tsv
└── 2025-2026_keyword_filter_stats.json
```

已有同名结果默认停止；新批次换目录或标签。`--force` 表示显式覆盖，不用于普通续跑。

当前适配器先排除小于 20 或大于 2,000 字符的句子，再检查关键词判定：排除词、人名误用、水稻相关词、生物概念/过程和 Os/LOC 模式。统计中的淘汰原因按首次命中判定计数，不是独立多标签。

历史统计：输入 1,207,889，保留 35,451，保留率约 2.94%；`NoRice=1,089,342`、`Blacklist=43,070`、`NoKeywords=25,664`、`RiceAsName=4,680`、`TooShort=7,849`、`TooLong=1,833`。

```bash
cat results/oger_input/keyword_filtered/2025-2026_keyword_filter_stats.json
wc -l results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.tsv
```

前置筛选已生成 OGER JSON，可以跳过旧 `oger-input`。不必将同一关键词规则再次作为新的去噪步骤重复执行。

### 7.2 按已有年份映射原样拆分

OGER 读取合并 JSON，另外两套工具读取年度 TSV。当前仓库未单独封装年度拆分入口，可使用以下代码。已有年度筛选文件时跳过；此代码不重新筛句、分句或编号：

```bash
python3 - <<'PY'
import csv
from pathlib import Path
base = Path("results/oger_input/keyword_filtered")
src = base / "2025-2026_keyword_filtered_sent.tsv"
mapping = base / "2025-2026_keyword_sentence_year_map.tsv"
out = Path("results/sentence_keyword_filtered")
years = (2025, 2026)
year_by_sid = {}
with mapping.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter="\t")
    assert {"Sentence_ID", "Year"} <= set(reader.fieldnames or []), "年份表头错误"
    for row in reader:
        sid, year = row["Sentence_ID"], int(row["Year"])
        assert sid not in year_by_sid, "年份映射重复: " + sid
        year_by_sid[sid] = year
rows = {year: [] for year in years}
seen = set()
with src.open(encoding="utf-8-sig") as f:
    for number, raw in enumerate(f, 1):
        line = raw.rstrip("\r\n")
        if not line:
            continue
        parts = line.split("\t", 2)
        assert len(parts) == 3 and all(parts), "三列格式错误: " + str(number)
        pmid, sid, text = parts
        assert "\t" not in text and sid not in seen, "正文含 Tab 或句子 ID 重复"
        assert sid in year_by_sid, "缺少年份: " + sid
        year = year_by_sid[sid]
        assert year in rows, "年份超出范围"
        seen.add(sid)
        rows[year].append(line + "\n")
assert seen == set(year_by_sid), "年份映射与句子集合不一致"
targets = {year: out / f"{year}_filtered_sent.txt" for year in years}
assert not any(p.exists() for p in targets.values()), "输出已存在，跳过或换目录"
out.mkdir(parents=True, exist_ok=True)
for year in years:
    with targets[year].open("x", encoding="utf-8", newline="\n") as f:
        f.writelines(rows[year])
    print(year, len(rows[year]), targets[year])
PY
wc -l results/sentence_keyword_filtered/*.txt
```

历史计数为 24,189 + 11,262 = 35,451。三个工具必须使用同一批句子 ID 和正文，不能把旧年度全量 JSON 与新筛选 TSV 混用。

<a id="oger"></a>
## 8. OGER 五轮标注

**代码：** `run_oger_five_passes.sh` 每轮调用 `annotation/call_oger.py`。

**需要变更：** 合并 JSON 路径、数据集标签、环境中的七份词典路径。标签只影响输出分组，不负责筛日期。

| 轮次 | 每轮共同加载 | 本轮另加 |
|---|---|---|
| co | Oryzabase gene + Supplementary gene | co 词典 |
| go | 同上 | go 词典 |
| to | 同上 | to 词典 |
| rto | 同上 | rto 词典 |
| variety | 同上 | variety 词典 |

基因标注已包含在每轮 OGER 内，无需另给这两份基因词典补跑一次。

```bash
bash -n run_oger_five_passes.sh
bash run_oger_five_passes.sh --dry-run \
  --input-file results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.json \
  --dataset-label 2025-2026-keyword-filtered
```

`bash -n` 无输出且退出码为 0 表示语法通过。dry-run 不启动 OGER，但会创建日志目录，缺词典时仍可能下载和解压，所以它不是绝对无写入的检查。

确认路径后正式运行：

```bash
mkdir -p logs
LOG_FILE="$PWD/logs/oger-keyword-filtered-$(date +%Y%m%d_%H%M%S).log"
nohup bash run_oger_five_passes.sh \
  --input-file results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.json \
  --dataset-label 2025-2026-keyword-filtered \
  > "$LOG_FILE" 2>&1 &
printf 'PID=%s\nLog=%s\n' "$!" "$LOG_FILE"
```

输出结构：

```text
results/oger/five_passes/<run_id>/
├── logs/run.log
└── 2025-2026-keyword-filtered/
    ├── co/<timestamp>/pubtator、bioc_json、processing.log
    ├── go/<timestamp>/...
    ├── to/<timestamp>/...
    ├── rto/<timestamp>/...
    └── variety/<timestamp>/...
```

记下本次 run 根目录到 `OGER_RUN_DIR`，不要只取某个 `pubtator/`。以下是历史已完成批次：

```bash
OGER_RUN_DIR="$PWD/results/oger/five_passes/20260921_162731_27405"
grep -rh --include='processing.log' \
  -E 'Using term lists:|Processing completed successfully' "$OGER_RUN_DIR"
```

新运行应替换 run ID。完成时应有 5 个 processing 日志最终成功消息及外层 `All OGER passes completed`，再结合错误和统计校验判断。

当前 `call_oger.py` 导出 BioC 和 PubTator，两种导出内部各调用 OGER；每轮最终成功消息为一次。五轮串行，内部固定 `-j 4`，没有可直接传入的 `--workers` 或 `PROCESS_THRESHOLD`。本手册保留这些实际行为。

本批次 35,451 × 5 = 177,255 个 PubTator 文件可包含空文件；文件数不能证明每句都命中实体。统计脚本会合并五轮重复基因提及。

<a id="other-annotation"></a>
## 9. SciSpacy 和 PhraseMatcher

### 9.1 SciSpacy

**代码：** 五个 `annotation/scispacy_match_{co,go,to,rto,variety}.py`。使用 SciSpacy 分词和 EntityRuler 匹配，神经 NER 等组件停用；当前不加载两套基因词典。

**需要变更：** 真实模型、五个三列词典、筛选后年度句子、独立输出路径。先按第 5.2 节准备配置：

```bash
RICEMIND_ENV_FILE="$PWD/configs/keyword_filtered.env.sh" \
  bash run_ricemind.sh config
mkdir -p logs
SCISPACY_LOG="$PWD/logs/scispacy-keyword-filtered-$(date +%Y%m%d_%H%M%S).log"
nohup env RICEMIND_ENV_FILE="$PWD/configs/keyword_filtered.env.sh" \
  bash run_ricemind.sh scispacy > "$SCISPACY_LOG" 2>&1 &
printf 'PID=%s\nLog=%s\n' "$!" "$SCISPACY_LOG"
```

输出为 `results/scispacy/keyword_filtered/scispacy_*_result/`，例如 `2025_filtered_sent_result.tsv`。每类两个年度 TSV，总计 10 个。当前代码会写回同名结果，重算应换输出根目录。

```bash
grep -c 'All files processed successfully' "$SCISPACY_LOG"
find results/scispacy/keyword_filtered -type f -name '*.tsv' -print
```

预期 5 个工具完成消息；完整性和坐标由后续统计校验进一步核对。

### 9.2 PhraseMatcher

**代码：** `annotation/single_dictionary_match_multi_process.py`，由作者另给的通用 Pipeline 脚本适配。

**需要变更：** 句子/结果路径，以及显式 `--dict-dir`。该脚本默认从 `RICEMIND_DICT_DIR` 平铺读取，不会通过 `DICT_PATHS` 自动发现迁移后的 `annotation/`。

```bash
RICEMIND_ENV_FILE="$PWD/configs/keyword_filtered.env.sh" \
  bash run_ricemind.sh phrase --dry-run \
  --input-dir "$PWD/results/sentence_keyword_filtered" \
  --dict-dir "$PWD/dict-dir/annotation" \
  --output-root "$PWD/results/phrase/keyword_filtered"
```

正式运行：

```bash
mkdir -p logs
PHRASE_LOG="$PWD/logs/phrase-keyword-filtered-$(date +%Y%m%d_%H%M%S).log"
nohup env RICEMIND_ENV_FILE="$PWD/configs/keyword_filtered.env.sh" \
  bash run_ricemind.sh phrase \
  --input-dir "$PWD/results/sentence_keyword_filtered" \
  --dict-dir "$PWD/dict-dir/annotation" \
  --output-root "$PWD/results/phrase/keyword_filtered" \
  > "$PHRASE_LOG" 2>&1 &
printf 'PID=%s\nLog=%s\n' "$!" "$PHRASE_LOG"
```

输出 `Rice-{CO,GO,TO,RTO,VARIETY}-annotation-dir/Rice.2025.sent.tsv` 等 10 个八列文件。

默认 `--model blank`、`--batch-size 1000`、`--min-term-length 3`，加入标准名和同义词，同词多 ID 保留首次映射。`--pass-existing` 可跳过同名文件；不带时会写回，不保证自动恢复失败任务。

`--synonyms-only` 限定第三列词汇，`--model en_core_web_md` 可选择原作者分词模型。两项同时设置仍不能消除原版全部差异，例如碰撞处理策略。未经确认不要在同一批次混换这些方法设置。

完成标志为 `PhraseMatcher 完成: files=10`；历史清理前标注行数 134,386，不能解释为不同实体总数。

<a id="clean"></a>
## 10. 分类黑名单清理

**代码：** `filtration/remove_noise.py`。清理命中规则的标注行，写出副本，保留原句和坐标，不重新标注。

**需要变更：** 确认三个工具本批次输入、独立清理输出、活动规则目录。

### 10.1 规则表

`dict-dir/filtering/blacklists/` 分为 gene、variety、co、go、to、rto 六个 `*_blacklist.tsv`。表头：

```text
enabled  category  entity_id  match_type  matched_text  standard_name  source
```

| 列 | 含义 |
|---|---|
| enabled | 1 启用、0 停用 |
| category | 须与分类文件名一致 |
| entity_id | 规范化标注编号 |
| match_type | `id` 按类别+ID 整体删除；`id_text` 只删该 ID 与指定文本组合 |
| matched_text | `id_text` 必填，精确且区分大小写；`id` 模式留空 |
| standard_name | 阅读用途，当前不参与删除判断 |
| source | 来源/依据，当前不参与删除判断 |

没有 reason 列。18 条 variety 规则来自旧脚本，3 条数字 gene 规则为本批次核查后的本地扩展，来源应分别记录。后者仅删除指定 ID 下的 `1/2/3`，不删除同 ID 的完整基因名称。

增加规则只编辑对应 TSV，无需改 Python；保留表头和 Tab 分隔、避免重复启用。高频、短名称或无 RAP 编号不能单独作为删除依据。未确认建议可保留为 `enabled=0`。

### 10.2 预览与正式执行

以下 `_v2` 是新重算示例；已有旧清理结果时不必仅为阅读手册重算：

```bash
OGER_RUN_DIR="$PWD/results/oger/five_passes/20260921_162731_27405"
CLEANED_DIR="$PWD/results/cleaned/keyword_filtered_v2"
bash run_ricemind.sh remove-noise --dry-run \
  --blacklist-dir "$PWD/dict-dir/filtering/blacklists" \
  --phrase-root "$PWD/results/phrase/keyword_filtered" \
  --scispacy-root "$PWD/results/scispacy/keyword_filtered" \
  --oger-root "$OGER_RUN_DIR" \
  --output-root "$CLEANED_DIR"
```

核实后使用相同参数去掉 `--dry-run`：

```bash
bash run_ricemind.sh remove-noise \
  --blacklist-dir "$PWD/dict-dir/filtering/blacklists" \
  --phrase-root "$PWD/results/phrase/keyword_filtered" \
  --scispacy-root "$PWD/results/scispacy/keyword_filtered" \
  --oger-root "$OGER_RUN_DIR" \
  --output-root "$CLEANED_DIR"
```

**显式传 `--blacklist-dir` 很重要。** 基础环境可能仍设有旧 `RICEMIND_NOISE_BLACKLIST_FILE`；省略选择参数时会进入旧单表模式，遗漏分类 gene 规则。

输出含 `oger/`、`scispacy/`、`phrasematcher/` 和 `_audit/`。审计保存规则副本、`summary.json`、逐类别和逐规则删除统计。输出必须与输入分离，非空输出会被拒绝，`--in-place` 已停用。

历史删除量 4,330（PhraseMatcher）、4,294（SciSpacy）、5,030（OGER）对应当时 18 条 variety 规则。启用 gene 规则后以新审计为准。OGER 原始删除行含五轮重复，不能与合并去重提及数直接相减比较。

<a id="statistics"></a>
## 11. 三工具统计

**代码：** `filtration/annotations_statistics.py`，不自动清理或重做标注。

**需要变更：** 清理批次、合并 TSV、年份映射、平铺词典视图、新统计目录。第 5.3 节先建立视图，不能假定 `--oger-dict-dir` 会递归读取 genes/ontology。

```bash
source ricemind_env.sh
CLEANED_DIR="$PWD/results/cleaned/keyword_filtered_v2"
OGER_STATS_DICT_DIR="$PWD/dict-dir/views/oger_flat"
STAT_DIR="$PWD/results/statistics/keyword_filtered/manual_$(date +%Y%m%d_%H%M%S)_$$"
python3 filtration/annotations_statistics.py \
  --start-year 2025 --end-year 2026 \
  --sentence-file "$PWD/results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.tsv" \
  --year-map "$PWD/results/oger_input/keyword_filtered/2025-2026_keyword_sentence_year_map.tsv" \
  --cleaned-root "$CLEANED_DIR" \
  --oger-dict-dir "$OGER_STATS_DICT_DIR" \
  --check-only
```

通过后正式执行，输出目录应尚未存在：

```bash
python3 filtration/annotations_statistics.py \
  --start-year 2025 --end-year 2026 \
  --sentence-file "$PWD/results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.tsv" \
  --year-map "$PWD/results/oger_input/keyword_filtered/2025-2026_keyword_sentence_year_map.tsv" \
  --cleaned-root "$CLEANED_DIR" \
  --oger-dict-dir "$OGER_STATS_DICT_DIR" \
  --output-dir "$STAT_DIR"
```

也可分别传 `--oger-root`、`--scispacy-root`、`--phrase-root`。不要把多个 OGER run 混入一个统计根目录。

| 输出 | 用途 |
|---|---|
| `all_sentences_annotations.jsonl` | 全句子和去重标注，**下游关联输入** |
| `multi_entity_sentences_2025-2026.jsonl` | 至少两种大类别的句子子集 |
| `annotation_counts.tsv` | 工具/类别的原始行、去重提及、命中句子、不同 ID |
| `tool_overlap.tsv` | 同位置/类别/ID 等条件下工具重合 |
| `gene_name_frequency.tsv` | 基因来源、文本频次、文献和示例 |
| `summary.json` | 总体/分年计数与输入来源 |

去重按句子 ID、位置、类别和实体 ID。OGER 五轮视为一种工具，零标注句子仍在分母。`is_multi_entity` 表示类别数量；`is_strict_reliable` 为描述字段，不因基因只有 OGER 支持就删除它。

完成标志为“统计完成”和输出路径。`--check-only` 只校验不写结果。历史统计为有标注句子 31,589、无标注 3,862、去重实体提及 208,603。关联阶段还会规范化和应用规则，不能混用不同阶段的提及计数。

<a id="reference"></a>
## 12. 参考资料、组学 JSON 与基因主表

这是可跨文献批次复用的参考分支。现有资料和构建报告完整时，直接使用，不必重新下载。

### 12.1 下载官方资料

**代码：** `build_dataset/download_omics_references.py`。需要变更参考目录时使用 `--data-dir`：

```bash
python3 build_dataset/download_omics_references.py \
  --data-dir "$PWD/sequence_data/reference"
```

下载当前官方 Oryzabase 快照，及固定 Ensembl Plants release 59、IRGSP-1.0 的 GFF3、DNA、cDNA、pep。manifest 保存 URL、文件名、大小、哈希和检查状态。Oryzabase 原始文件保留，另建 UTF-8 TSV 副本。

已有 manifest 时复用其 Oryzabase 快照；换全新目录重新下载可能得到其他日期的导出。不要把新快照重命名成作者旧的日期以掩盖版本差异。本批次为 `OryzabaseGeneListEn_20261010010113.txt` 及其 `.utf8.tsv`，区别于作者旧的 2025-07-02 文件。

### 12.2 生成组学 JSON

**代码：** `build_dataset/build_rice_multi_omics.py`。

```bash
python3 build_dataset/build_rice_multi_omics.py \
  --data-dir "$PWD/sequence_data/reference" \
  --output "$PWD/sequence_data/rice_multi_omics.json"
```

输入 manifest 要完整，文件哈希须匹配。输出 `rice_multi_omics.json`、`rice_multi_omics_build_report.json`，已有输出默认停止；重算另选 `--output`，`--force` 为显式替换。

JSON 保存序列、转录本、坐标和索引，范围为 Oryzabase RAP 条目中具有参考 DNA/cDNA 的记录；该数量不等同于水稻全基因组基因总数。原表中无 RAP 或未匹配序列的条目仍需在后续参考整合中单独保留。

### 12.3 基因主表和候选索引

**代码：** `build_dataset/build_gene_master_universal.py`。当前采用 universal 版，不要紧接着再执行较早的 `build_gene_master.py` 覆盖主表。

先查四项自动发现的输入，并校验：

```bash
source ricemind_env.sh
python3 - <<'PY'
from pathlib import Path
from build_dataset.build_gene_master_universal import FILES
for role, filename in FILES.items():
    if role != "output_json":
        path = Path(filename)
        print(role, "存在" if path.is_file() else "缺少", path)
PY
python3 build_dataset/build_gene_master_universal.py --check-only
```

自动发现优先使用参考 manifest 中的 UTF-8 Oryzabase、`sequence_data/rice_multi_omics.json`、`asset/protein_gene_mapping.txt` 和活动 Supplementary 词典。也可完整指定：

```bash
python3 build_dataset/build_gene_master_universal.py \
  --omics-json "$PWD/sequence_data/rice_multi_omics.json" \
  --oryzabase-file "$PWD/sequence_data/reference/OryzabaseGeneListEn_20261010010113.utf8.tsv" \
  --protein-mapping "$PWD/asset/protein_gene_mapping.txt" \
  --supp-dict "$PWD/dict-dir/oger/genes/supplementary_gene_oger_dict.tsv" \
  --output-dir "$PWD/standard_gene"
```

Oryzabase 日期换版时替换参数，或使用自动发现。输出：

```text
standard_gene/
├── Unified_Gene_Master.json
├── Unified_Gene_Alias_Index.json
└── Unified_Gene_Master_build_report.json
```

新输出与旧主表应隔离；已有文件默认拒绝覆盖。若另用 `--output-dir`，关联步骤显式传入该目录的主表和索引。

本批次 49,345 条记录由 RAP 15,897、无 RAP 的 Oryzabase 6,367、Supplementary 27,081 组成。记录数不能解释为已验证独立生物学基因数。多义别名保留候选；当前没有仅凭名字把全部 Supplementary 条目合并到 RAP。

<a id="associations"></a>
## 13. 文献关联构建与核查

### 13.1 构建关联

**代码：** `build_GTA/build_nlp_associations.py`。

**需要变更：** 统计批次、主表和索引、分类规则、年份和新输出目录。读取统计后的 `all_sentences_annotations.jsonl`，不能直接传 PubTator、年度 TSV 或 OGER JSON 数组。

```bash
source ricemind_env.sh
STAT_DIR="$PWD/results/statistics/keyword_filtered/20260929_165826_18558"
python3 build_GTA/build_nlp_associations.py \
  --stats-dir "$STAT_DIR" \
  --master-file "$PWD/standard_gene/Unified_Gene_Master.json" \
  --index-file "$PWD/standard_gene/Unified_Gene_Alias_Index.json" \
  --blacklist-dir "$PWD/dict-dir/filtering/blacklists" \
  --start-year 2025 --end-year 2026 \
  --check-only
```

上例是本次已完成统计路径；新运行替换为实际批次。通过后执行：

```bash
python3 build_GTA/build_nlp_associations.py \
  --stats-dir "$STAT_DIR" \
  --master-file "$PWD/standard_gene/Unified_Gene_Master.json" \
  --index-file "$PWD/standard_gene/Unified_Gene_Alias_Index.json" \
  --blacklist-dir "$PWD/dict-dir/filtering/blacklists" \
  --start-year 2025 --end-year 2026
```

默认新建 `results/associations/keyword_filtered/<run_id>/`；也可用 `--output-dir` 指定未存在目录。记录 `[OUTPUT]` 到 `ASSOC_DIR`。

当前处理按句内实体组合构建 GTA、GVA、TVA，Evidence_Code 为 `NLP_Cooccurrence`。唯一编号候选才映射，未唯一定位时保留原 ID、候选和状态，RAP 留空。默认关闭名称回退；`--allow-symbol-fallback` 会改变映射策略，本文默认命令不启用。

关联阶段再次应用当前分类黑名单，排除结果进入 `normalized_sentences.jsonl`、基因审计和规则快照。旧统计文件本身不被改写，不能说其计数已自动同步更新。

一次生成第 1 节全部主关联结果。`First_Mention_Year` 仅表示当前输入范围内最早年份标签，不等于历史首次发现时间。

**不需要再串接旧 `map_nlp_rap_id.py` 或 `add_trends_to_nlp.py`。** 当前生成器已经整合映射和 Trend，旧脚本仍读取 `Original_ID` 等旧字段。

完成标志为发布的输出目录和 `association_summary.json` 的 `status=complete`。失败的 `.building-*` 目录或 `FAILED.json` 不能作为完成结果。

### 13.2 核查材料

**代码：** `build_GTA/prepare_association_review.py`。

```bash
ASSOC_DIR="$PWD/results/associations/keyword_filtered/20261014_095526_184013_31655"
python3 build_GTA/prepare_association_review.py \
  --association-dir "$ASSOC_DIR"
```

程序检查输出哈希、上下文、计数和 Trend 组合一致性，然后新建 `review/`。已有目录会停止，另一次抽样用新 `--output-dir`，不要覆盖填写过的表。

输出 `gene_mapping_review.tsv`、`gene_term_frequency.tsv`、`association_review_sample.tsv`、`review_summary.json`。默认各关系 50 行、seed=20261014，可用 `--sample-per-type`、`--seed` 修改并记录。

核查意见不自动改黑名单、主表或结果。当前本地初审材料标记 `expert_confirmed=false`，不能称作专家真值或整库准确率。根据复现范围，新增语义筛选、重新分句、人工映射是单独决策，不能默认设成继续流程的前置条件。

<a id="coverage"></a>
## 14. 公共库比较与差集导出

### 14.1 公共参考成品

当前使用作者 [Zenodo 19702501](https://zenodo.org/records/19702501) 发布的 `Unified_Rice_GTA_Database.tsv.tar.gz`。服务器已经准备好，可跳过下载和解压。新部署将压缩包放入 `sequence_data/reference/public_gta/zenodo_19702501/`。

对本次同一个作者包：

```bash
(
set -e
cd /path/to/RiceMind-engineering/sequence_data/reference/public_gta/zenodo_19702501
test -s Unified_Rice_GTA_Database.tsv.tar.gz
printf '%s\n' 'b55d0570308ec6f874e9d2e2bb08705b  Unified_Rice_GTA_Database.tsv.tar.gz' | md5sum -c -
gzip -t Unified_Rice_GTA_Database.tsv.tar.gz
tar -tzf Unified_Rice_GTA_Database.tsv.tar.gz
tar -xzf Unified_Rice_GTA_Database.tsv.tar.gz
head -n 2 Unified_Rice_GTA_Database.tsv
)
```

校验值固定对应本次包；更换记录版本时核对新来源的校验信息。公共 TSV 是比较参考，不能当作本次文献挖掘输出。

**`build_GTA/build_gta_database.py` 从 Oryzabase、RAP-DB、Ensembl、Planteome 的原始公共资料重建对照库。它不读取 NLP 关联表，也不将两者拼成新的最终库。** 已使用作者成品时无需补跑。专门重建公共库需要另备四来源原始文件，核对旧固定日期、字段和映射，属于独立分支。

### 14.2 覆盖比较

**代码：** `build_GTA/compare_gta_coverage.py`。

```bash
source ricemind_env.sh
ASSOC_DIR="$PWD/results/associations/keyword_filtered/20261014_095526_184013_31655"
PUBLIC_FILE="$PWD/sequence_data/reference/public_gta/zenodo_19702501/Unified_Rice_GTA_Database.tsv"
python3 -c 'import pandas, matplotlib, matplotlib_venn; print("Dependencies OK")'
python3 build_GTA/compare_gta_coverage.py \
  --association-dir "$ASSOC_DIR" --public-file "$PUBLIC_FILE" --check-only
python3 build_GTA/compare_gta_coverage.py \
  --association-dir "$ASSOC_DIR" --public-file "$PUBLIC_FILE"
```

预检仅核对文件/必需表头，不能替代全表、依赖和绘图验证。正式读取 `NLP_Rice_GTA_Trend.tsv`，不要替换为逐句主表。

新目录 `results/coverage/<run_id>/` 输出 `comparison.log`、`comparison_manifest.json`、`Detailed_Coverage_Venn_Diagram_v2.png`。完成以成功清单 `status=complete` 和日志为依据。

保留作者比较口径：`RAP_ID.startswith("Os")` 选择记录，按唯一 RAP 编号比基因集合，按精确 `(RAP_ID, Ontology_ID)` 比关联。GO 组用 GO:，PO 组用 PO:，TO 组含 TO:、RTO:、CO_。

全体 78,868 对与比较中的 53,107 对不同；后者满足 Os 前缀条件。总集合还包含三组以外的本体前缀，不能将 GO/PO/TO 三组相加直接当总体。

### 14.3 差集和证据

**代码：** `build_GTA/export_coverage_details.py`。

```bash
python3 build_GTA/export_coverage_details.py \
  --association-dir "$ASSOC_DIR" \
  --public-file "$PUBLIC_FILE"
```

默认新建 `ASSOC_DIR/coverage_details/`；已有目录会停止。另一次导出用新 `--output-dir`，无需删除已交付结果。

输出共有/独有基因、关联组合、`ontology_prefix_summary.tsv`、差集原句及 manifest。最近检查的 `regulates`、`NoNorm` 等前缀就是既有差集文件的内容观察。

NLP-only 表示当前公共快照与精确匹配口径下的差集，不能直接称为生物学新发现。比较还受到词典/本体范围、版本和 ID 规范化差异影响。GVA、TVA 未因 GTA 比较自动获得公共库验证。

<a id="delivery"></a>
## 15. 结果核验和交付

### 15.1 查看文件

```bash
ASSOC_DIR="$PWD/results/associations/keyword_filtered/20261014_095526_184013_31655"
ls -lh \
  "$ASSOC_DIR/NLP_Rice_GTA_Database.tsv" \
  "$ASSOC_DIR/NLP_Rice_GVA_TVA_Database.tsv" \
  "$ASSOC_DIR/NLP_Rice_GTA_Trend.tsv" \
  "$ASSOC_DIR/association_summary.json" \
  "$ASSOC_DIR/coverage_details/gta_pairs_nlp_only_sentence_evidence.tsv" \
  "$ASSOC_DIR/coverage_details/coverage_details_manifest.json"
```

`ls` 证明存在和大小；来源/计数仍按报告和检查结果解释。统计 TSV 应使用解析器，含引号/多行字段时 `wc -l` 不一定等于记录数。年度三列句子一行一句，可用 `wc -l`。

### 15.2 只读校验主结果哈希和行数

```bash
python3 - "$ASSOC_DIR" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
s = json.loads((root / "association_summary.json").read_text(encoding="utf-8"))
assert s.get("status") == "complete", "关联批次未完成"
for name, metadata in s["outputs"].items():
    h = hashlib.sha256()
    with (root / name).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    assert h.hexdigest() == metadata["sha256"], "输出已改变: " + name
c = s["counts"]
expected = {
    "NLP_Rice_GTA_Database.tsv": c["gta_rows"],
    "NLP_Rice_GVA_TVA_Database.tsv": c["gva_rows"] + c["tva_rows"],
    "NLP_Rice_GTA_Trend.tsv": c["unique_gta_pairs"],
}
for name, wanted in expected.items():
    with (root / name).open(encoding="utf-8", newline="") as f:
        actual = sum(1 for _ in csv.DictReader(f, delimiter="\t"))
    assert actual == wanted, (name, actual, wanted)
    print(name, actual)
print("关联输出哈希和行数检查通过")
PY
```

该代码不重算关联。Excel 预览应另存副本，保留原 TSV，避免自动转换编号、日期或特殊字符。

### 15.3 交付范围与打包

建议交付关联批次完整目录、coverage 图/日志/manifest、基因主表构建报告、参考版本、词典/规则版本、环境记录、手册和复现范围说明。完整复算还需另保留原始文献、句子、三工具标注、参考数据和主表；精简包未包含这些输入时明确说明。

以下示例只打包当前结果与部分追溯资料，不删除原目录：

```bash
mkdir -p delivery
PACKAGE="$PWD/delivery/RiceMind-results-2025-2026-$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$PACKAGE" \
  results/associations/keyword_filtered/20261014_095526_184013_31655 \
  results/coverage/20261016_110551_638065_22509 \
  standard_gene/Unified_Gene_Master_build_report.json \
  sequence_data/reference/reference_manifest.json \
  REPRODUCTION_SCOPE.md \
  docs/RiceMind_使用手册.md
sha256sum "$PACKAGE" > "$PACKAGE.sha256"
```

新批次应替换历史 run ID。是否删除旧 49 GB 未筛选 OGER 结果取决于归档需求，不属于标注/建库必经步骤。

<a id="rerun"></a>
## 16. 修改后从哪一步重跑

| 变更 | 修改位置 | 从哪一步重新运行 | 可以复用 |
|---|---|---|---|
| 移动目录，内容未改 | 环境配置和路径参数 | 路径预检即可 | 已有全部业务成果 |
| 新文献/年份 | 上游输入、年份参数、批次路径 | prepare 及相关下游 | 未变参考资料 |
| 改分句或 HTML 处理 | 转换器/上游 | prepare 后各步骤 | 原始文献、参考资料 |
| 改关键词规则 | keyword_filter.py/筛选参数 | 前置筛选、受影响标注和下游 | 原始句子和参考；未经集合核对不混用旧标注 |
| 改 OGER 词典 | dict-dir/oger | 受影响 OGER 标注、清理/统计/关联/比较 | 同一原句上未改的另两工具 |
| 改三列词典 | dict-dir/annotation | 受影响 SciSpacy/PhraseMatcher 及下游 | OGER 和未变工具 |
| 改黑名单 | 对应 *_blacklist.tsv | 规范重算为清理→新统计→关联→比较；生成器也可对旧统计再应用规则，须记录口径 | 三套原始标注 |
| 改基因主表/映射参考 | 主表输入和参数 | 主表→关联→核查/比较/导出 | 原实体标注和统计 |
| 改公共对照快照 | 公共参考文件 | 比较/差集导出 | 文献关联 |
| 仅改文档/展示 | 相应文档/图 | 对应展示步骤 | 全部业务数据 |

新年份要同步：上游年度标签、前置筛选年份、年度拆分中的 years/文件名、统计年份与合并文件参数、关联年份及批次标签。SciSpacy/PhraseMatcher 的目录只放本批次文件。旧 `oger-input/oger` 入口仍硬编码 2025/2026，不宜当新年份一键入口。

没有新数据或规则改变时，目录整理和时间推移不要求重新启动整个流程。

<a id="scripts"></a>
## 17. 项目全部业务脚本索引

### 17.1 配置与入口

| 文件 | 功能 |
|---|---|
| ricemind_config.py | Python 路径解析，单独执行可打印配置 |
| ricemind_env.sh | 本机真实路径；机器迁移主要编辑这里 |
| ricemind_env.sh.example | 早期配置示例；规范目录应按本文第 5 节补齐 |
| run_ricemind.sh | 前半程包装入口 |
| run_oger_five_passes.sh | 当前五轮 OGER 入口 |

### 17.2 annotation

| 文件 | 作用与本批次位置 |
|---|---|
| pubtator_to_sentence_tsv.py | 补充的文献转句子适配器，主流程使用 |
| call_oger.py | 多词典 OGER 调用，五轮入口内部使用 |
| scispacy_match_co.py | CO EntityRuler 匹配，使用 |
| scispacy_match_go.py | GO 匹配，使用 |
| scispacy_match_to.py | TO 匹配，使用 |
| scispacy_match_rto.py | RTO 匹配，使用 |
| scispacy_match_variety.py | 品种匹配，使用 |
| single_dictionary_match_multi_process.py | 适配后 PhraseMatcher，使用；历史文件名不表示当前自动多进程 |
| tsv_2_txt_json.py | 单文件/年度句子转 OGER JSON；前置筛选已输出 JSON 时跳过 |
| tsv_2_txt_json1.py | 上述转换兼容入口，不重复运行 |
| oger_annotate_input_dic.py | 旧单词典调用，五轮完成后无需再跑 |
| clean_terms_debug.py | 清理旧自建词典的纯特殊符号词条，不清理标注结果 |
| delete_lines.sh | awk 版旧词典清理 |
| annotate_all_by_python.sh | 旧分片词典标注/合并；包含旧分片、相对调用和固定日期合并，不适配当前五轮 |

### 17.3 filtration

| 文件 | 作用与本批次位置 |
|---|---|
| keyword_filter.py | 保存句子判定规则；直接执行仍读取旧多实体 JSONL 配置 |
| keyword_filter_pre_oger.py | 导入上面的判定函数，筛年度句子并输出 TSV/JSON/映射/统计 |
| remove_noise.py | 三工具标注完成后，按外部分类规则清理副本 |
| annotations_statistics.py | 清理后合并去重统计，输出下游全句 JSONL |

### 17.4 build_dataset

| 文件 | 作用与本批次位置 |
|---|---|
| download_omics_references.py | 当前官方参考下载和 manifest，已有可复用 |
| build_rice_multi_omics.py | 当前组学 JSON 生成器 |
| build_gene_master_universal.py | 当前主表、Supplementary 整合、候选索引和报告 |
| extract_local_omics.py | 原组学分支，依赖 pandas/Biopython 和旧路径；当前不需顺序再跑 |
| build_gene_master.py | 较早主表实现，不能当 universal 的后续必跑步骤 |

### 17.5 build_GTA

| 文件 | 作用与本批次位置 |
|---|---|
| build_nlp_associations.py | 文献关联和 Trend、审计，已完成 |
| prepare_association_review.py | 检查和抽样核查材料，已完成生成 |
| compare_gta_coverage.py | 公共/NLP 精确集合比较和 Venn，已完成 |
| export_coverage_details.py | 差集清单和原句证据，已完成，当前主流程终点 |
| build_gta_database.py | 四来源公共参考重建独立分支，本批次直接用作者成品 |
| map_nlp_rap_id.py | 旧映射，读取 Original_ID；当前生成器已整合，不串联 |
| add_trends_to_nlp.py | 旧趋势补充，同样不接到当前生成器后面重复运行 |

### 17.6 analyse 和辅助资料

| 文件/目录 | 功能与前提 |
|---|---|
| analyse/extract_evidence.py | 按 gene/trait 查证据，仍读旧 annotations/Normalization 及部分本体模式；不能默认支持当前 normalized_entities，优先查已生成关联主表 |
| analyse/classify_supplementary_genes.py | 名称子串比较；依赖 supplementary_gene_samples.jsonl 和 validation_target_id，主流程未自动生成该样本 |
| analyse/analyze_novel_genes_pubs.py | 同类样本的 year/journal 分布，仍固定 2021 阈值，不能自动解释为新年份的近五年 |
| gene_list/ | 作者名称清单及人工边界修订差异，不是删除黑名单 |
| asset/protein_gene_mapping.txt | 参考映射资源，无需“运行” |
| tests/ | 工程契约测试，不是数据生产的某一阶段 |

两个 Supplementary 分析把名称不重叠的一类称为 novel；名称子串差异本身不能证明新基因。历史记录未确认这些可选分析全部执行，不能为“补齐全部脚本”直接运行或替代主流程收尾。

<a id="troubleshooting"></a>
## 18. 常见问题

| 现象 | 处理 |
|---|---|
| zip FileNotFoundError | 先在服务器核实上传和实际文件名；电脑下载不代表服务器已有 |
| gzip unexpected end of file | 查大小、gzip -t 和路径；本次曾混淆根目录完整包与 /tmp 的失败下载 |
| 模型缺 config.cfg | 配置包内部真实模型数据目录，见第 4 节 |
| transformer factory 缺失 | 检查模型组件依赖和当前 Python；disable 仍可能加载组件 |
| co/go 词典不存在 | 查五个 RICEMIND_*_DICT；PhraseMatcher 显式 --dict-dir |
| 临时路径被覆盖，读回原始句子 | 包装脚本重新加载环境文件；用第 5.2 节批次配置 |
| 统计缺 OGER 词典 | 第 5.3 节平铺软链接视图及显式 --oger-dict-dir |
| 清理进入单文件模式 | 明确 --blacklist-dir；旧 NOISE_BLACKLIST_FILE 会选择旧单表 |
| dry-run 没有实体 | 仅预览；去掉 --dry-run 才执行 |
| shell Done 是否成功 | 只证明进程退出，需看最终日志和结构校验 |
| tail -f 不退出 | 它持续监听；Ctrl+C 停止 tail，不会停止独立 nohup 任务 |
| 输出目录已存在 | 换新目录，不先删除成果绕过保护 |
| 主表 0 条却打印成功 | 可能跑旧版，先 --help 核对新参数及四项输入，保留失败产物 |
| 1/2/3 标为 gene | 查实际结果和精确 ID+文本规则，不按整个 ID 删除完整基因名 |
| regulates、NoNorm 出现于关联 ID | 保留来源和影响观察；未确认方案不直接批量删本体或关系 |
| SciSpacy 很快完成 | 当前是词典匹配，重组件停用；快慢不能证明准确率 |

状态查看示例，日志名须换成真实值：

```bash
pgrep -af 'run_ricemind.sh scispacy|scispacy_match|run_oger_five_passes|call_oger.py'
tail -n 50 logs/实际日志文件.log
stat -c '日志最后修改时间: %y' logs/实际日志文件.log
```

mtime 只表示最后修改时间，单独不能证明成功。未来将日志统一放 logs/，旧根目录日志可在保留关联关系后归档。

<a id="scope"></a>
## 19. 复现边界与核对来源

集中路径、外置规则、日志、失败停止、独立输出目录属于工程支持。以下内容可能影响结果，应单独说明：

- 文献转句子是补充实现，缺少作者同一分句实现时不能声称边界完全一致。
- PhraseMatcher 的分词、标准名纳入和同词多 ID 策略与作者另给脚本存在差异。
- 统计已适配五轮和全句分母，与原字段/口径不能未经核对等同。
- 当前主表/关联保留候选、默认关闭名字回退，并使用本地新增数字 gene 规则。
- Oryzabase 快照为 2026 年，作者旧输入日期不同。
- 作者部分人工检查和删除未完整记录，不能从公开资料重建所有决定。

详细对照见 [复现范围说明](../REPRODUCTION_SCOPE.md)。本手册不自动增加新清理、消歧、重新分句或语义关系判断。

每批保存：上游来源/年份、句子和映射哈希、代码版本、环境/模型版本、七份 OGER 和五份三列词典版本、规则快照、参考 manifest、各阶段实际输出目录和日志。旧流程文档的“当前下一步”具有历史时效，最新完成状态应以已确认日志为准。

本手册依据两个包装脚本、配置模块，以及五个业务目录内源码编写。服务器状态依据用户成功日志及文件清单，本地没有重新计算服务器全数据。本文运行命令为 Linux bash；Windows 编辑上传脚本应为 UTF-8、LF，避免 BOM/CRLF 问题。

主要源码依据：

- [统一入口](../run_ricemind.sh)、[OGER 入口](../run_oger_five_passes.sh)、[Python 配置](../ricemind_config.py)。
- [前置筛选](../filtration/keyword_filter_pre_oger.py)、[清理](../filtration/remove_noise.py)、[统计](../filtration/annotations_statistics.py)。
- [参考下载](../build_dataset/download_omics_references.py)、[组学](../build_dataset/build_rice_multi_omics.py)、[主表](../build_dataset/build_gene_master_universal.py)。
- [文献关联](../build_GTA/build_nlp_associations.py)、[核查](../build_GTA/prepare_association_review.py)、[公共库独立分支](../build_GTA/build_gta_database.py)。
- [覆盖比较](../build_GTA/compare_gta_coverage.py)、[差集导出](../build_GTA/export_coverage_details.py)。

外部软件来源：[OGER 官方仓库](https://github.com/OntoGene/OGER)、[SciSpacy 0.5.4 官方说明](https://github.com/allenai/scispacy/blob/v0.5.4/README.md)、[spaCy 加载说明](https://spacy.io/api/language)。数据来源与版本以本批次已保存 manifest 为准。
