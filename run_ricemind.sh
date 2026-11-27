#!/usr/bin/env bash
set -Eeuo pipefail

# One command entry point for the server workflow.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${RICEMIND_ENV_FILE:-$ROOT_DIR/ricemind_env.sh}"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

export RICEMIND_BASE_DIR="${RICEMIND_BASE_DIR:-$ROOT_DIR}"
cd "$ROOT_DIR"

usage() {
    cat <<'EOF'
RiceMind runner

Usage:
  bash run_ricemind.sh config       显示当前解析到的所有路径
  bash run_ricemind.sh prepare      PubTator -> 句子 TSV
  bash run_ricemind.sh oger-input   句子 TSV -> OGER JSON 输入
  bash run_ricemind.sh keyword-filter-pre-oger  合并并筛选年度句子，生成 OGER 输入
  bash run_ricemind.sh oger         对 2025/2026 JSON 输入运行 OGER
  bash run_ricemind.sh phrase       运行 RiceMind 内置 PhraseMatcher 五类词典匹配
  bash run_ricemind.sh remove-noise 自动读取分类黑名单并清理三类标注结果
  bash run_ricemind.sh annotations-statistics  汇总去噪后的三工具结果并去重统计
  bash run_ricemind.sh basic        依次执行 prepare 和 oger-input
  bash run_ricemind.sh scispacy     运行 5 个 SciSpacy 词典匹配脚本

精确日期筛选示例：
  bash run_ricemind.sh prepare --date-map /path/pmid_date.tsv \
      --start-date 2025-03-01 --end-date 2026-09-30

第一次使用：
  cp ricemind_env.sh.example ricemind_env.sh
  vi ricemind_env.sh
  bash run_ricemind.sh config
EOF
}

require_path() {
    local label="$1"
    local path="$2"
    if [[ ! -e "$path" ]]; then
        echo "[ERROR] $label 不存在: $path" >&2
        echo "请在 ricemind_env.sh 中设置对应路径。" >&2
        exit 2
    fi
}

run_scispacy() {
    local config_output
    config_output="$(python3 - <<'PY'
import ricemind_config as c
print(c.SCISPACY_MODEL)
for key, path in c.DICT_PATHS.items():
    print(f"{key}\t{path}")
PY
)"

    local model_path
    model_path="$(printf '%s\n' "$config_output" | head -n 1)"
    require_path "SciSpacy 模型" "$model_path"

    while IFS=$'\t' read -r key path; do
        [[ -z "$key" ]] && continue
        require_path "${key} 词典" "$path"
    done < <(printf '%s\n' "$config_output" | tail -n +2)

    python3 annotation/scispacy_match_co.py
    python3 annotation/scispacy_match_go.py
    python3 annotation/scispacy_match_to.py
    python3 annotation/scispacy_match_rto.py
    python3 annotation/scispacy_match_variety.py
}

run_oger() {
    local oger_config
    oger_config="$(python3 - <<'PY'
import ricemind_config as c
print(c.OGER_PACKAGE)
print(c.OGER_TERMLIST)
print(c.OGER_INPUT_DIR)
print(c.OGER_OUTPUT_DIR)
PY
)"
    local package_path termlist_path input_dir output_dir
    package_path="$(printf '%s\n' "$oger_config" | sed -n '1p')"
    termlist_path="$(printf '%s\n' "$oger_config" | sed -n '2p')"
    input_dir="$(printf '%s\n' "$oger_config" | sed -n '3p')"
    output_dir="$(printf '%s\n' "$oger_config" | sed -n '4p')"
    require_path "OGER Python 包" "$package_path"
    require_path "OGER 词典" "$termlist_path"

    for year in 2025 2026; do
        local input_file="$input_dir/${year}_filtered_sent.json"
        require_path "${year} OGER 输入" "$input_file"
        python3 annotation/oger_annotate_input_dic.py \
            --input "$input_file" \
            --output "$output_dir" \
            --termlist "$termlist_path"
    done
}

command="${1:-help}"
shift || true

case "$command" in
    config|show-config)
        python3 ricemind_config.py
        ;;
    prepare)
        python3 annotation/pubtator_to_sentence_tsv.py "$@"
        ;;
    oger-input)
        python3 annotation/tsv_2_txt_json.py --start-year 2025 --end-year 2026 "$@"
        ;;
    keyword-filter-pre-oger)
        python3 filtration/keyword_filter_pre_oger.py "$@"
        ;;
    oger)
        run_oger
        ;;
    basic)
        python3 annotation/pubtator_to_sentence_tsv.py
        python3 annotation/tsv_2_txt_json.py --start-year 2025 --end-year 2026
        ;;
    scispacy)
        run_scispacy
        ;;
    phrase|phrasematcher)
        python3 annotation/single_dictionary_match_multi_process.py "$@"
        ;;
    remove-noise)
        python3 filtration/remove_noise.py "$@"
        ;;
    annotations-statistics)
        python3 filtration/annotations_statistics.py "$@"
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo "未知命令: $command" >&2
        usage >&2
        exit 2
        ;;
esac
