# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
'''
(Alterome_RDF) [ywliu@localhost gta]$ python compare_gta_coverage.py
Loading Public Database: Unified_Rice_GTA_Database.tsv...
Loading NLP Trend Database: NLP_Rice_GTA_Trend.tsv...

========================================
 维度 1: 基因级别覆盖率 (RAP_ID)
========================================
公共数据库包含总数:  50465
NLP提取包含总数:   7324
两者共有(一致)数量:  7292
NLP发现的全新关联:   32 (占比 0.4%)

========================================
 维度 2: 总体 GTA 关联级别覆盖率
========================================
公共数据库包含总数:  297419
NLP提取包含总数:   439267
两者共有(一致)数量:  15272
NLP发现的全新关联:   423995 (占比 96.5%)

========================================
 维度 3.1: GO (基因功能) 关联覆盖率
========================================
公共数据库包含总数:  176572
NLP提取包含总数:   169684
两者共有(一致)数量:  8376
NLP发现的全新关联:   161308 (占比 95.1%)

========================================
 维度 3.2: PO (植物解剖/发育) 关联覆盖率
========================================
公共数据库包含总数:  89910
NLP提取包含总数:   27549
两者共有(一致)数量:  2774
NLP发现的全新关联:   24775 (占比 89.9%)

========================================
 维度 3.3: TO (农艺性状) 关联覆盖率
========================================
公共数据库包含总数:  30937
NLP提取包含总数:   135019
两者共有(一致)数量:  4122
NLP发现的全新关联:   130897 (占比 96.9%)

Generating Venn diagrams...
✅ 细分可视化大图已生成至当前配置的 GTA 目录。


'''




import argparse
import csv
import hashlib
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import GTA_DATA_DIR, RESULTS_DIR, SEQUENCE_DATA_DIR

# ==========================================
# 配置路径（统一由 ricemind_config.py 管理）
# ==========================================
base_dir = str(GTA_DATA_DIR)

# 公共数据库金标准文件 (知识级)
db_gta_file = os.path.join(base_dir, "Unified_Rice_GTA_Database.tsv")

# 【核心修改点】更换为新生成的 NLP 知识关联级/趋势文件，摒弃有冗余的句级文件
nlp_gta_file = os.path.join(base_dir, "NLP_Rice_GTA_Trend.tsv")

def print_stats(name, db_set, nlp_set):
    """辅助函数：计算并打印覆盖率统计信息"""
    overlap = db_set.intersection(nlp_set)
    novel = nlp_set - db_set
    nlp_total = len(nlp_set) if len(nlp_set) > 0 else 1 # 防止除以0
    
    print(f"\n" + "="*40)
    print(f" {name}")
    print("="*40)
    print(f"公共数据库包含总数:  {len(db_set)}")
    print(f"NLP提取包含总数:   {len(nlp_set)}")
    print(f"两者共有(一致)数量:  {len(overlap)}")
    print(f"NLP发现的全新关联:   {len(novel)} (占比 {len(novel)/nlp_total*100:.1f}%)")
    
    return len(db_set - nlp_set), len(novel), len(overlap)

def compare_coverage():
    import pandas as pd
    from matplotlib_venn import venn2
    import matplotlib.pyplot as plt

    print(f"Loading Public Database: {os.path.basename(db_gta_file)}...")
    df_db = pd.read_csv(db_gta_file, sep='\t', dtype=str).fillna("")
    
    print(f"Loading NLP Trend Database: {os.path.basename(nlp_gta_file)}...")
    df_nlp = pd.read_csv(nlp_gta_file, sep='\t', dtype=str).fillna("")

    # 核心过滤：只比较拥有标准 RAP_ID (以Os开头) 的有效数据
    # 这会自然过滤掉 Supplementary_geneID，确保比对基准绝对公平
    valid_db = df_db[df_db['RAP_ID'].str.startswith('Os')]
    valid_nlp = df_nlp[df_nlp['RAP_ID'].str.startswith('Os')]

    # ==========================================
    # 宏观维度: 基因 (Gene) 和 总体关联 (Overall GTA)
    # ==========================================
    db_genes = set(valid_db['RAP_ID'])
    nlp_genes = set(valid_nlp['RAP_ID'])
    
    # 提取 (RAP_ID, Ontology_ID) 组成的关联边 Edge
    db_edges = set(zip(valid_db['RAP_ID'], valid_db['Ontology_ID']))
    nlp_edges = set(zip(valid_nlp['RAP_ID'], valid_nlp['Ontology_ID']))

    # ==========================================
    # 细分维度: GO, PO, TO 的关联层过滤
    # ==========================================
    def filter_edges(edges, prefix_tuple):
        return {e for e in edges if str(e[1]).startswith(prefix_tuple)}

    db_go = filter_edges(db_edges, ('GO:',))
    nlp_go = filter_edges(nlp_edges, ('GO:',))

    db_po = filter_edges(db_edges, ('PO:',))
    nlp_po = filter_edges(nlp_edges, ('PO:',))

    # TO包含 TO:, RTO:, CO_ 前缀
    db_to = filter_edges(db_edges, ('TO:', 'RTO:', 'CO_'))
    nlp_to = filter_edges(nlp_edges, ('TO:', 'RTO:', 'CO_'))

    # 打印终端统计数据并获取画图用的子集大小
    stats_gene = print_stats("维度 1: 基因级别覆盖率 (RAP_ID)", db_genes, nlp_genes)
    stats_edge = print_stats("维度 2: 总体 GTA 关联级别覆盖率", db_edges, nlp_edges)
    stats_go = print_stats("维度 3.1: GO (基因功能) 关联覆盖率", db_go, nlp_go)
    stats_po = print_stats("维度 3.2: PO (植物解剖/发育) 关联覆盖率", db_po, nlp_po)
    stats_to = print_stats("维度 3.3: TO (农艺性状) 关联覆盖率", db_to, nlp_to)

    # ==========================================
    # 绘制韦恩图 (2行 x 3列 的组合大图)
    # ==========================================
    print("\nGenerating Venn diagrams...")
    plt.figure(figsize=(18, 12))
    plt.suptitle("RiceMind GTA Coverage Analysis (Public DBs vs. NLP Extracted Trend)", fontsize=18, y=0.95)

    # 1. 基因级别 (第一行左侧)
    plt.subplot(2, 3, 1)
    venn2(subsets=stats_gene, set_labels=('Public DBs', 'NLP Extracted'))
    plt.title("1. Gene Coverage (RAP_ID)", fontsize=14)

    # 2. 总体GTA级别 (第一行中间)
    plt.subplot(2, 3, 2)
    venn2(subsets=stats_edge, set_labels=('Public DBs', 'NLP Extracted'))
    plt.title("2. Overall GTA Edge Coverage", fontsize=14)
    
    # 隐藏第一行最右侧的空白子图以保持视觉平衡
    ax = plt.subplot(2, 3, 3)
    ax.axis('off')

    # 3. GO级别 (第二行左侧)
    plt.subplot(2, 3, 4)
    if sum(stats_go) > 0:
        venn2(subsets=stats_go, set_labels=('Public DBs', 'NLP Extracted'))
    plt.title("3. GO Edge Coverage", fontsize=14)

    # 4. PO级别 (第二行中间)
    plt.subplot(2, 3, 5)
    if sum(stats_po) > 0:
        venn2(subsets=stats_po, set_labels=('Public DBs', 'NLP Extracted'))
    plt.title("4. PO Edge Coverage", fontsize=14)

    # 5. TO级别 (第二行右侧)
    plt.subplot(2, 3, 6)
    if sum(stats_to) > 0:
        venn2(subsets=stats_to, set_labels=('Public DBs', 'NLP Extracted'))
    plt.title("5. TO Edge Coverage", fontsize=14)

    # 保存高分辨率图片
    output_img = os.path.join(base_dir, "Detailed_Coverage_Venn_Diagram_v2.png")
    plt.savefig(output_img, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"✅ 细分可视化大图已生成并保存至: {output_img}")

class _Tee:
    """Write the original console report to the console and a UTF-8 log."""

    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, value):
        self.console.write(value)
        self.log.write(value)
        return len(value)

    def flush(self):
        self.console.flush()
        self.log.flush()


def _input_file(parser, value, label):
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        parser.error("Missing or empty {}: {}".format(label, path))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle, delimiter="\t"), [])
    missing = {"RAP_ID", "Ontology_ID"} - set(header)
    if missing:
        parser.error("{} lacks columns: {}".format(path, ", ".join(sorted(missing))))
    return path


def _file_info(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def main(argv=None):
    """Adapt paths and reporting; preserve the author's set comparisons."""
    global base_dir, db_gta_file, nlp_gta_file
    parser = argparse.ArgumentParser(
        description="Compare the author-published public GTA reference with an explicitly selected NLP batch.")
    parser.add_argument(
        "--public-file", type=Path,
        default=SEQUENCE_DATA_DIR / "reference/public_gta/zenodo_19702501/Unified_Rice_GTA_Database.tsv",
        help="Public GTA TSV; defaults to the downloaded Zenodo reference.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--association-dir", type=Path,
                           help="Selected completed batch containing NLP_Rice_GTA_Trend.tsv.")
    selection.add_argument("--nlp-file", type=Path, help="Explicit NLP trend TSV.")
    parser.add_argument("--output-dir", type=Path,
                        help="New result directory; existing directories are rejected.")
    parser.add_argument("--check-only", action="store_true",
                        help="Check input files and required headers; write no outputs.")
    args = parser.parse_args(argv)
    chosen_nlp = args.nlp_file or (
        args.association_dir / "NLP_Rice_GTA_Trend.tsv"
        if args.association_dir else Path(nlp_gta_file))
    public = _input_file(parser, args.public_file, "public reference")
    nlp = _input_file(parser, chosen_nlp, "NLP trend")
    print("[INPUT] Public reference: " + str(public), flush=True)
    print("[INPUT] NLP trend: " + str(nlp), flush=True)
    if args.check_only:
        print("[CHECK] Input files and required headers passed; no outputs written.")
        return 0

    output = (args.output_dir or (
        RESULTS_DIR / "coverage" /
        (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + str(os.getpid()))
    )).expanduser().resolve()
    if output.exists():
        parser.error("Output already exists; choose a new directory: " + str(output))
    inputs = dict(public=_file_info(public), nlp_trend=_file_info(nlp))
    output.mkdir(parents=True, exist_ok=False)
    base_dir, db_gta_file, nlp_gta_file = str(output), str(public), str(nlp)
    os.environ.setdefault("MPLBACKEND", "Agg")
    with (output / "comparison.log").open("x", encoding="utf-8", newline="\n") as log:
        with redirect_stdout(_Tee(sys.stdout, log)), redirect_stderr(_Tee(sys.stderr, log)):
            print("[INPUT] Public reference: " + str(public))
            print("[INPUT] NLP trend: " + str(nlp))
            print("[METHOD] Original Os-prefix filtering and exact ID set comparisons.")
            print("[NOTE] NLP-only means absent from this public snapshot; biological novelty is not established.")
            try:
                compare_coverage()
            except Exception as exc:
                print("[ERROR] {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
                if isinstance(exc, ImportError):
                    print("Install plotting dependencies: python3 -m pip install pandas matplotlib matplotlib-venn",
                          file=sys.stderr)
                return 2
    manifest = dict(
        status="complete", inputs=inputs,
        completed_at=datetime.now().astimezone().isoformat(),
        outputs=["comparison.log", "Detailed_Coverage_Venn_Diagram_v2.png"],
        method=dict(
            gene_filter="RAP_ID startswith Os (author's original predicate)",
            gene_comparison="unique RAP_ID",
            association_comparison="unique exact (RAP_ID, Ontology_ID)",
            go_prefixes=["GO:"], po_prefixes=["PO:"], to_prefixes=["TO:", "RTO:", "CO_"]),
        notes=["Uses the supplied integrated public reference; source database integration was not rerun.",
               "No new annotation filtering, sentence splitting or gene mapping is performed.",
               "Historical logs at the top of this script do not describe this execution.",
               "NLP-only entries are candidates absent from this public snapshot, not verified new discoveries."])
    (output / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[OUTPUT] " + str(output), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
