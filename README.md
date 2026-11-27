# RiceMind Engineering Adaptation

基于 [muhaha2/RiceMind](https://github.com/muhaha2/RiceMind) 的独立工程整理版，提供统一配置、句子处理、三工具标注、分类去噪、统计、基因规范化、共现关联与公共库比较。研究方法与原贡献归原作者，不声称逐条重现论文结果。

**新部署从 [完整资源版指南](docs/BUNDLED_WORKFLOW.md) 开始。**

本地完整包集中十二份标注词典、六类黑名单、蛋白—基因映射、作者基因参考名单、固定 Oryzabase 快照与 35,451 条筛选后句子。完整包同时含 1,207,889 条年度句子、固定参考资料和既有基因主表；另提供对应独立附件，方便按需取得。模型提供下载/安装命令。GitHub 源码包与本地完整包的区别见 [数据权利说明](DATA_LICENSE.md)。

~~~text
PubTator/年度句子 → 前置筛选 → 统一句子输入
  ├─ 合并 JSON → OGER 五轮（两套 gene + 每轮一套其他词典）
  └─ 年度 TSV → SciSpacy EntityRuler / PhraseMatcher
  → 分类去噪 → 合并统计 → 基因主表与编号对齐
  → GTA/GVA/TVA 共现 → 公共快照比较 → 差集和原句证据
~~~

文献检索下载来自项目外上游。NLP_Cooccurrence 是同句共现候选；公共快照差集不等于新发现。

## 最小启动

~~~bash
python3 tools/check_resources.py
python3 tools/prepare_sentence_data.py \
  --filtered-dir datasets/2025-2026-keyword-filtered \
  --output-dir results/corpora/current
~~~

上述数据入口需本地完整包，或将有权限的对应数据附件安装到 datasets/。纯源码使用自己的年度句子/PubTator 入口，见指南。NLP 依赖与模型安装、批次配置和后续命令均在指南。可先执行合成样本工程测试：

~~~bash
python3 -m unittest discover -s tests -p 'test_*.py'
~~~

## 目录与文档

| 位置 | 职责 |
|---|---|
| annotation/ | 分句、OGER、SciSpacy、PhraseMatcher |
| filtration/ | 前置筛句、规则清理、合并统计 |
| build_dataset/ | 官方资料、组学、基因主表 |
| build_GTA/ | 关联、公共库独立分支、比较与导出 |
| analyse/ | 旧格式专项分析，尚未全部适配 |
| tools/ | 同批句子整理、资源校验 |
| dict-dir/ | 三列/六列词典及分类规则 |
| asset/、gene_list/ | 映射与作者参考名单 |
| datasets/、sequence_data/reference/ | 句子与固定参考资料 |
| resources/、docs/、tests/ | 来源散列、使用说明、工程测试 |

- [与原版的差异](docs/CHANGES_FROM_UPSTREAM.md)
- [详细使用手册](docs/RiceMind_使用手册.md)
- [数据资源](docs/DATA_RESOURCES.md)
- [来源与授权](docs/ATTRIBUTION.md)
- [验证范围](docs/VALIDATION.md) 和 [已知限制](docs/KNOWN_LIMITATIONS.md)
- [发布到 GitHub](docs/PUBLISH_TO_GITHUB.md)

保留原 [Apache-2.0 LICENSE](LICENSE) 和 [NOTICE](NOTICE)。补充分句、PhraseMatcher 选项、统计重写、数字基因规则和候选映射等均明确记录。基线是本地保留原始 ZIP，对应上游提交未确认。旧服务器完整标注与最终结果未全部同步本地，本包提供复跑资料，不冒充新完成的实验。

