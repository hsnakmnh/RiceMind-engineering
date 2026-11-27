# 句子数据入口

本地完整包的 2025-2026-keyword-filtered/ 携带 35,451 条筛选句子及年份映射；GitHub 源码包保留统计与校验清单，文献正文独立管理。

使用本地数据附件时放入该目录，按 docs/BUNDLED_WORKFLOW.md 生成 OGER JSON 与年度 TSV。无正文附件时可使用 examples/sentences/ 检查格式，或从自己的年度句子/PubTator 开始。

corpus_manifest.json 记录处理阶段和版本；filter_stats.json 是历史筛选统计，不表示本次重新处理过完整百万条语料。文本原有权利见 DATA_LICENSE.md。
