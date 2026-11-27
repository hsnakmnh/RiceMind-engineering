# 数据与资源

主包携带：

| 位置 | 内容 |
|---|---|
| dict-dir/annotation/ | 五份三列词典，供 SciSpacy/PhraseMatcher |
| dict-dir/oger/genes/ | Oryzabase、supplementary 两套六列基因词典 |
| dict-dir/oger/ontology/ | co/go/to/rto/variety 五套六列词典 |
| dict-dir/filtering/blacklists/ | 六类黑名单，21 条启用规则 |
| asset/protein_gene_mapping.txt | 上游已有的蛋白—基因映射 |
| gene_list/ | 作者三份字段切分/修正参考，非自动删除清单 |
| sequence_data/reference/ | 固定 Oryzabase 原始及 UTF-8 快照、参考清单 |
| datasets/2025-2026-keyword-filtered/ | 35,451 条句子、年份映射、历史统计和校验值 |
| resources/manifest.json | 来源、用途、原始/活动文件 SHA-256 |

OGER 来自 [作者 dict 包](https://github.com/muhaha2/RiceMind/blob/main/annotation/dict.tar.gz)，三列词典另由作者提供。仅 variety 三列活动文件去掉明确首行表头，其余词典保留原件字节。不要互换三列/六列词典。

完整句子附件含 2025 年 807,372 条、2026 年 400,517 条。由本地两个 OGER JSON 数组恢复三列 TSV，保留 ID/正文。2025 与仍存原 TSV 逐行一致；2026 原 TSV 本地缺失，仅验证恢复记录和条数。附件不含原始 PubTator 文献。

参考运行附件含四份 Ensembl release 59 gz、公共 GTA、既有组学 JSON、49,345 条基因主表和索引。报告的个人绝对路径改为相对路径，计数与实体内容保留，清单记录原件散列及转换。

reference_manifest 的 complete 描述历史下载批次。主包仅含其中 Oryzabase 项，其余由下载器或参考包补齐；资源校验入口见 [使用指南](BUNDLED_WORKFLOW.md)。采用 2026 年 Oryzabase，与作者原 2025 年快照不同。

如不取参考包：

~~~bash
python3 build_dataset/download_omics_references.py
python3 build_dataset/build_rice_multi_omics.py
python3 build_dataset/build_gene_master_universal.py
~~~

公共 GTA 来自 [Zenodo 19702501](https://zenodo.org/records/19702501)，可单独下载：

~~~bash
(
set -e
mkdir -p sequence_data/reference/public_gta/zenodo_19702501
cd sequence_data/reference/public_gta/zenodo_19702501
curl --fail --location --retry 5 \
  -o Unified_Rice_GTA_Database.tsv.tar.gz \
  "https://zenodo.org/records/19702501/files/Unified_Rice_GTA_Database.tsv.tar.gz?download=1"
echo "b55d0570308ec6f874e9d2e2bb08705b  Unified_Rice_GTA_Database.tsv.tar.gz" | md5sum -c -
tar -xzf Unified_Rice_GTA_Database.tsv.tar.gz
)
~~~

模型、环境、原始文章、大日志和旧标注不纳入 Git。大型附件使用 Releases，避免触及 [GitHub 普通文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。数据适用原提供方条款，见 [数据权利说明](../DATA_LICENSE.md)。

