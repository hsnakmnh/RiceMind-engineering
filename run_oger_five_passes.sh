#!/usr/bin/env bash
set -Eeuo pipefail

# RiceMind's dict.tar.gz contains five main ontology dictionaries and two
# gene dictionaries. This runner makes five sequential OGER passes per input
# dataset (one year by default): each pass uses one ontology dictionary plus both gene dictionaries.
# This is an interpretation of the author's "run it five times" instruction.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${RICEMIND_ENV_FILE:-$ROOT_DIR/ricemind_env.sh}"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi
cd "$ROOT_DIR"

PYTHON_BIN="${RICEMIND_PYTHON:-python3}"
DICT_URL="https://raw.githubusercontent.com/muhaha2/RiceMind/main/annotation/dict.tar.gz"
DICT_ARCHIVE="${RICEMIND_OGER_DICT_ARCHIVE:-$ROOT_DIR/annotation/dict.tar.gz}"
DICT_DIR="${RICEMIND_OGER_DICT_DIR:-$ROOT_DIR/dict-dir/oger}"
GENE_DICT_DIR="${RICEMIND_OGER_GENE_DIR:-$DICT_DIR/genes}"
ONTOLOGY_DICT_DIR="${RICEMIND_OGER_ONTOLOGY_DIR:-$DICT_DIR/ontology}"
DRY_RUN=false
YEARS=()
INPUT_FILE=""
DATASET_LABEL=""
CUSTOM_INPUT=false

usage() {
    cat <<'EOF'
Usage:
  bash run_oger_five_passes.sh [--dry-run] [YEAR ...]
  bash run_oger_five_passes.sh --input-file PATH [--dataset-label NAME] [--dry-run]

Examples:
  bash run_oger_five_passes.sh --dry-run 2025 2026
  bash run_oger_five_passes.sh 2025 2026
  bash run_oger_five_passes.sh --dry-run --input-file results/oger_input/keyword_filtered/2025-2026_keyword_filtered_sent.json --dataset-label 2025-2026-keyword-filtered

Default years: 2025 2026

The script downloads annotation/dict.tar.gz if it is missing, extracts its
seven OGER dictionaries, then runs five sequential passes for each input dataset.
Each pass combines one of CO/GO/TO/RTO/variety with the two gene dictionaries.
EOF
}

while (($#)); do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --input-file)
            if (($# < 2)); then
                echo "[ERROR] --input-file requires a path." >&2
                exit 2
            fi
            INPUT_FILE="$2"
            shift 2
            ;;
        --dataset-label)
            if (($# < 2)); then
                echo "[ERROR] --dataset-label requires a name." >&2
                exit 2
            fi
            DATASET_LABEL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            while (($#)); do
                YEARS+=("$1")
                shift
            done
            ;;
        -* )
            echo "[ERROR] Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            YEARS+=("$1")
            shift
            ;;
    esac
done

if [[ -n "$INPUT_FILE" ]]; then
    if ((${#YEARS[@]} > 0)); then
        echo "[ERROR] Use either --input-file or YEAR arguments, not both." >&2
        exit 2
    fi
    CUSTOM_INPUT=true
    if [[ -z "$DATASET_LABEL" ]]; then
        DATASET_LABEL="${INPUT_FILE##*/}"
        DATASET_LABEL="${DATASET_LABEL%.json}"
    fi
    if [[ ! "$DATASET_LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
        echo "[ERROR] Invalid dataset label: $DATASET_LABEL" >&2
        exit 2
    fi
elif [[ -n "$DATASET_LABEL" ]]; then
    echo "[ERROR] --dataset-label is only valid together with --input-file." >&2
    exit 2
else
    if ((${#YEARS[@]} == 0)); then
        YEARS=(2025 2026)
    fi
    for year in "${YEARS[@]}"; do
        if [[ ! "$year" =~ ^[0-9]{4}$ ]]; then
            echo "[ERROR] Year must be four digits: $year" >&2
            exit 2
        fi
    done
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[ERROR] Python executable not found: $PYTHON_BIN" >&2
    echo "Set RICEMIND_PYTHON if your environment uses a different command." >&2
    exit 2
fi

# Read input/output paths from the same central configuration as the other
# RiceMind scripts, so ricemind_env.sh overrides are honored.
mapfile -t CONFIG_PATHS < <("$PYTHON_BIN" - <<'PY'
from ricemind_config import OGER_INPUT_DIR, OGER_OUTPUT_DIR
print(OGER_INPUT_DIR)
print(OGER_OUTPUT_DIR)
PY
)
if ((${#CONFIG_PATHS[@]} != 2)); then
    echo "[ERROR] Could not resolve OGER paths from ricemind_config.py." >&2
    exit 2
fi
INPUT_DIR="${RICEMIND_OGER_INPUT_DIR:-${CONFIG_PATHS[0]}}"
OGER_OUTPUT_ROOT="${RICEMIND_OGER_OUTPUT_DIR:-${CONFIG_PATHS[1]}}"

DATASET_LABELS=()
INPUT_FILES=()
if [[ "$CUSTOM_INPUT" == true ]]; then
    if [[ "$INPUT_FILE" != /* ]]; then
        INPUT_FILE="$ROOT_DIR/$INPUT_FILE"
    fi
    DATASET_LABELS+=("$DATASET_LABEL")
    INPUT_FILES+=("$INPUT_FILE")
else
    for year in "${YEARS[@]}"; do
        DATASET_LABELS+=("$year")
        INPUT_FILES+=("$INPUT_DIR/${year}_filtered_sent.json")
    done
fi

ontology_dicts=(
    co_oger_dict.tsv
    go_oger_dict.tsv
    to_oger_dict.tsv
    rto_oger_dict.tsv
    variety_oger_dict.tsv
)
gene_dicts=(
    oryzabase_gene_oger_dict.tsv
    supplementary_gene_oger_dict.tsv
)

# Prefer the normalized genes/ and ontology/ layout.  The flat layout remains
# a compatibility fallback for older RiceMind checkouts.
if [[ ! -s "$GENE_DICT_DIR/${gene_dicts[0]}" || ! -s "$GENE_DICT_DIR/${gene_dicts[1]}" || \
      ! -s "$ONTOLOGY_DICT_DIR/${ontology_dicts[0]}" ]]; then
    if [[ -s "$DICT_DIR/${gene_dicts[0]}" && -s "$DICT_DIR/${gene_dicts[1]}" && \
          -s "$DICT_DIR/${ontology_dicts[0]}" ]]; then
        GENE_DICT_DIR="$DICT_DIR"
        ONTOLOGY_DICT_DIR="$DICT_DIR"
    fi
fi

required_dict_paths=()
for name in "${ontology_dicts[@]}"; do
    required_dict_paths+=("$ONTOLOGY_DICT_DIR/$name")
done
for name in "${gene_dicts[@]}"; do
    required_dict_paths+=("$GENE_DICT_DIR/$name")
done

all_dicts_present=true
for path in "${required_dict_paths[@]}"; do
    [[ -s "$path" ]] || all_dicts_present=false
done

if [[ "$all_dicts_present" != true ]]; then
    if [[ ! -s "$DICT_ARCHIVE" ]]; then
        echo "[INFO] Dictionary archive not found; downloading the RiceMind author archive."
        mkdir -p "$(dirname "$DICT_ARCHIVE")"
        download_tmp="${DICT_ARCHIVE}.part.$$"
        trap 'rm -f "${download_tmp:-}"' EXIT
        if command -v curl >/dev/null 2>&1; then
            curl --fail --location --retry 3 --output "$download_tmp" "$DICT_URL"
        elif command -v wget >/dev/null 2>&1; then
            wget --tries=3 --output-document="$download_tmp" "$DICT_URL"
        else
            echo "[ERROR] Install curl or wget, or set RICEMIND_OGER_DICT_ARCHIVE." >&2
            exit 2
        fi
        mv "$download_tmp" "$DICT_ARCHIVE"
        trap - EXIT
    fi

    if ! command -v tar >/dev/null 2>&1; then
        echo "[ERROR] tar is required to unpack $DICT_ARCHIVE" >&2
        exit 2
    fi
    archive_entries="$(tar -tzf "$DICT_ARCHIVE")"
    for name in "${ontology_dicts[@]}" "${gene_dicts[@]}"; do
        if ! printf '%s\n' "$archive_entries" | grep -Fx "dict/$name" >/dev/null; then
            echo "[ERROR] Expected dict/$name is missing from $DICT_ARCHIVE" >&2
            exit 2
        fi
    done
    mkdir -p "$DICT_DIR"
    tar -xzf "$DICT_ARCHIVE" --strip-components=1 -C "$DICT_DIR"
    # The author archive is flat. Use the extracted flat files for this run.
    GENE_DICT_DIR="$DICT_DIR"
    ONTOLOGY_DICT_DIR="$DICT_DIR"
    required_dict_paths=()
    for name in "${ontology_dicts[@]}" "${gene_dicts[@]}"; do
        required_dict_paths+=("$DICT_DIR/$name")
    done
fi

for path in "${required_dict_paths[@]}"; do
    if [[ ! -s "$path" ]]; then
        echo "[ERROR] Required OGER dictionary is missing or empty: $path" >&2
        exit 2
    fi
done

if [[ ! -f "$ROOT_DIR/annotation/call_oger.py" ]]; then
    echo "[ERROR] Missing OGER runner: $ROOT_DIR/annotation/call_oger.py" >&2
    exit 2
fi

for input_file in "${INPUT_FILES[@]}"; do
    if [[ ! -s "$input_file" ]]; then
        echo "[ERROR] OGER input file is missing or empty: $input_file" >&2
        echo "Create it first with: bash run_ricemind.sh oger-input" >&2
        exit 2
    fi
done

if [[ "$DRY_RUN" != true ]]; then
    if ! "$PYTHON_BIN" -c 'from oger.ctrl.run import run; from oger.ctrl import parameters' >/dev/null; then
        echo "[ERROR] OGER is not importable in $PYTHON_BIN." >&2
        echo "Activate the environment where OGER is installed, or set RICEMIND_PYTHON." >&2
        exit 2
    fi
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
RUN_ROOT="$OGER_OUTPUT_ROOT/five_passes/$RUN_ID"
mkdir -p "$RUN_ROOT/logs"
LOG_FILE="$RUN_ROOT/logs/run.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[INFO] Input directory: $INPUT_DIR"
echo "[INFO] Dictionary directory: $DICT_DIR"
echo "[INFO] Gene dictionaries: $GENE_DICT_DIR"
echo "[INFO] Ontology dictionaries: $ONTOLOGY_DICT_DIR"
echo "[INFO] Output directory: $RUN_ROOT"
echo "[INFO] Datasets: ${DATASET_LABELS[*]}"
echo "[INFO] Five passes per dataset; runs are sequential."
echo "[INFO] Log: $LOG_FILE"

target_dicts=(co go to rto variety)
for index in "${!INPUT_FILES[@]}"; do
    dataset_label="${DATASET_LABELS[$index]}"
    input_file="${INPUT_FILES[$index]}"
    for target in "${target_dicts[@]}"; do
        target_list="$ONTOLOGY_DICT_DIR/${target}_oger_dict.tsv"
        output_dir="$RUN_ROOT/$dataset_label/$target"
        cmd=(
            "$PYTHON_BIN" annotation/call_oger.py
            --input "$input_file"
            --termlist
            "$GENE_DICT_DIR/oryzabase_gene_oger_dict.tsv"
            "$GENE_DICT_DIR/supplementary_gene_oger_dict.tsv"
            "$target_list"
            --output "$output_dir"
        )

        echo ""
        echo "[INFO] Pass: dataset=$dataset_label, dictionary=$target"
        if [[ "$DRY_RUN" == true ]]; then
            printf '[DRY-RUN]'
            printf ' %q' "${cmd[@]}"
            printf '\n'
        else
            mkdir -p "$output_dir"
            "${cmd[@]}"
        fi
    done
done

if [[ "$DRY_RUN" == true ]]; then
    echo "[INFO] Dry run complete; OGER was not started."
else
    echo "[INFO] All OGER passes completed."
    echo "[INFO] Results are grouped by dataset and dictionary under: $RUN_ROOT"
fi
