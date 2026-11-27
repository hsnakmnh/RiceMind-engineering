# 完整资源版使用入口

本页对应 2026-11-27 整理包。旧服务器已完成的结果仍然有效，不需要为了目录适配重新标注。研究方法差异见 [修改说明](CHANGES_FROM_UPSTREAM.md)。

## 1. 包的用途

| 包 | 内容 |
|---|---|
| RiceMind-engineering-complete-20261127.zip | 代码、十二份词典、六类规则、映射和作者参考名单、35,451 条筛选后句子、1,207,889 条完整句子、固定序列/公共 GTA、既有组学与主表/索引、文档及测试 |
| RiceMind-sentences-full-2025-2026-20261127.zip | 筛选前 1,207,889 条年度句子和来源/校验清单 |
| RiceMind-reference-runtime-20261127.zip | 四份参考序列、公共 GTA 快照、已生成组学 JSON 和基因主表/索引、报告与校验清单 |

本地完整包已包括后两个独立附件的全部资料，可直接解压进入 RiceMind-engineering 根目录。另备 RiceMind-engineering-github-source-20261127.zip：含代码、词典、映射、固定 Oryzabase 与处理说明，省去文献正文、全量序列和生成物，适合 Git 管理。使用该源码包时可按需补充独立附件；参考包解压到项目根目录。不要覆盖现有服务器不同版本的主表。

模型和软件不随包携带。数据包可以与代码通过 GitHub Releases 分开管理；文献文本公开再分发范围尚未逐篇核实，见 [DATA_LICENSE.md](../DATA_LICENSE.md)。本地完整包不等于所有内容均获得统一开放许可。

## 2. 环境与资源检查

以下为 Linux bash 命令，在项目根目录执行。建议独立 Python 3.10 环境。requirements-runtime.txt 是版本约束清单；本次未重新安装完整 NLP 环境，不能称为已验证的环境锁文件。

~~~bash
python3 -m pip install -r requirements-runtime.txt
python3 -m pip install \
  "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_scibert-0.5.4.tar.gz"
python3 -m pip check
cp -n ricemind_env.sh.example ricemind_env.sh
python3 tools/check_resources.py
~~~

将 ricemind_env.sh 中 RICEMIND_SCISPACY_MODEL 改为直接包含 config.cfg 的目录：

~~~bash
python3 - <<'PY'
from pathlib import Path
import en_core_sci_scibert
for p in Path(en_core_sci_scibert.__file__).resolve().parent.rglob("config.cfg"):
    print(p.parent)
PY
source ricemind_env.sh
~~~

OGER 从活动 Python 环境自动发现。SciSpacy 0.5.4 依赖 spaCy 3.7 系列，见 [版本源码](https://github.com/allenai/scispacy/blob/v0.5.4/setup.py)。SciBERT 还需要 spacy-transformers；disable 停止组件执行时仍会加载组件，见 [spaCy 官方说明](https://spacy.io/api/top-level#spacy.load)。

## 3. 句子入口：四选一

**使用随包筛选后句子，接着进行标注：**

~~~bash
python3 tools/prepare_sentence_data.py \
  --filtered-dir datasets/2025-2026-keyword-filtered \
  --output-dir results/corpora/current
~~~

输出 combined.tsv（三列，无表头）、year_map.tsv、oger.json、annual/2025_filtered_sent.txt、annual/2026_filtered_sent.txt、filter_stats.json、preparation_report.json。

年度条数为 24,189 和 11,262。此模式保留原有 ID 与正文，不重新分句或筛选。输出目录已存在会拒绝覆盖；重跑时换一个新目录。

**完整句子包或自己的年度三列 TSV：**

~~~bash
python3 tools/prepare_sentence_data.py \
  --sentence-dir rice_sentences --start-year 2025 --end-year 2026 \
  --output-dir results/corpora/refiltered
~~~

读取 2025_filtered_sent.txt、2026_filtered_sent.txt，运行既有 keyword_filter_pre_oger.py。完整句子的历史文件名含 filtered，不代表已经完成这一步。

**只有年度 OGER JSON：** 将 --sentence-dir 改为 --oger-json-dir。文件名为 2025_filtered_sent.json、2026_filtered_sent.json，每个数组对象含 id/text。由 PMID_序号形式的 id 恢复三列 TSV，不重新分句，再运行既有筛选。

**自己的原始 PubTator：**

~~~bash
python3 tools/prepare_sentence_data.py \
  --pubtator-dir RICE-pubtator-dir --start-year 2025 --end-year 2026 \
  --output-dir results/corpora/from-pubtator
~~~

调用现有 pubtator_to_sentence_tsv.py 后再筛选；默认排除标题。文献文件名用 *.pmid-pmcid.txt，年份来自文件名。项目没有包括 PubMed 检索下载上游。重新从文献分句可能与历史边界不同，应独立跑整批标注，避免混用旧结果。

## 4. 三项标注用同一份句子

~~~bash
mkdir -p configs
cp -n configs/keyword-filtered.env.sh.example configs/keyword-filtered.env.sh
export RICEMIND_ENV_FILE="$PWD/configs/keyword-filtered.env.sh"
source "$RICEMIND_ENV_FILE"
bash run_ricemind.sh config

bash run_oger_five_passes.sh --dry-run \
  --input-file "$RICEMIND_CORPUS_DIR/oger.json" \
  --dataset-label 2025-2026-keyword-filtered
bash run_oger_five_passes.sh \
  --input-file "$RICEMIND_CORPUS_DIR/oger.json" \
  --dataset-label 2025-2026-keyword-filtered
bash run_ricemind.sh scispacy
bash run_ricemind.sh phrase
~~~

OGER 在 results/runs/keyword_filtered/oger/five_passes/时间戳/。其余在同批次根目录 scispacy/ 和 phrase/。批次配置在基础配置之后设置句子与输出，避免加载环境文件覆盖临时变量。

每轮 OGER 使用两份基因词典，加一份 co/go/to/rto/variety 词典。SciSpacy 与 PhraseMatcher 共用五份三列词典，这两个入口没有额外两套基因词典。OGER 应有五轮成功和 All OGER passes completed；SciSpacy 应有五次 All files processed successfully；PhraseMatcher 对两年五类应 files=10。dry-run 仅打印计划。

## 5. 去噪与统计

将 OGER_RUN 的最后一段改为实际运行输出目录：

~~~bash
OGER_RUN="$RICEMIND_OGER_OUTPUT_DIR/five_passes/实际时间戳"
python3 filtration/remove_noise.py \
  --blacklist-dir dict-dir/filtering/blacklists \
  --oger-root "$OGER_RUN" \
  --scispacy-root "$RICEMIND_SCISPACY_OUTPUT_ROOT" \
  --phrase-root "$RICEMIND_PHRASE_OUTPUT_ROOT" \
  --output-root "$RICEMIND_RESULTS_DIR/cleaned" --dry-run
~~~

确认预览后去掉末尾 --dry-run 正式执行；随后：

~~~bash
python3 filtration/annotations_statistics.py \
  --sentence-file "$RICEMIND_CORPUS_DIR/combined.tsv" \
  --year-map "$RICEMIND_CORPUS_DIR/year_map.tsv" \
  --cleaned-root "$RICEMIND_RESULTS_DIR/cleaned" \
  --oger-dict-dir dict-dir/oger \
  --output-dir "$RICEMIND_RESULTS_DIR/statistics"
~~~

统计器支持 genes/ontology 分类布局，也兼容旧平铺布局，无需手建词典链接。当前 18 条 variety 规则来自作者原脚本，3 条数字 gene 规则为本地确认扩展。gene 为 ID+匹配文本规则，保留同一基因正常名称；规则去噪不能替代人工准确率评估。

## 6. 参考资料与数据库后半程

已解压参考包时：

~~~bash
python3 tools/check_resources.py --with-references
~~~

如果要从官方资料重新生成，主包已固定 Oryzabase 快照，下载器补齐四份 Ensembl release 59 文件：

~~~bash
python3 build_dataset/download_omics_references.py
python3 build_dataset/build_rice_multi_omics.py
python3 build_dataset/build_gene_master_universal.py --check-only
python3 build_dataset/build_gene_master_universal.py
~~~

两种方式选一种。生成脚本保护旧输出；已有主表时不应直接重复首次生成命令。公共 GTA 的单独下载命令见 [资源说明](DATA_RESOURCES.md)。

然后构建关联并导出比较结果：

~~~bash
python3 build_GTA/build_nlp_associations.py \
  --stats-dir "$RICEMIND_RESULTS_DIR/statistics" \
  --output-dir "$RICEMIND_RESULTS_DIR/associations"
python3 build_GTA/prepare_association_review.py \
  --association-dir "$RICEMIND_RESULTS_DIR/associations"
python3 build_GTA/compare_gta_coverage.py \
  --association-dir "$RICEMIND_RESULTS_DIR/associations"
python3 build_GTA/export_coverage_details.py \
  --public-file sequence_data/reference/public_gta/zenodo_19702501/Unified_Rice_GTA_Database.tsv \
  --association-dir "$RICEMIND_RESULTS_DIR/associations"
~~~

review/ 提供人工抽样检查。主要文件 NLP_Rice_GTA_Database.tsv（逐句）、NLP_Rice_GTA_Trend.tsv（聚合）、NLP_Rice_GVA_TVA_Database.tsv（基因/性状与品种共现）、association_summary.json 与 coverage_details/ 存在该 associations 目录。

这些关联是 NLP_Cooccurrence 候选；公共库差集不等于生物学新发现。本地没有完整同步旧服务器的全量标注/最终关联，故主包不冒充新的全流程运行成果。

更细的参数、可选公共库独立分支、旧工具与重跑范围见 [详细使用手册](RiceMind_使用手册.md)。

