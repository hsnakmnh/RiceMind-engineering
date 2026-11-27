#!/usr/bin/env python3
"""Central path configuration for the RiceMind pipeline.

All paths used by the maintained Python stages should come from this module.
The repository itself is the default base directory, so the same checkout can
run on a server without editing every script.  Any value can be overridden by
an environment variable before launching a stage.
"""

from __future__ import annotations

import os
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def _path(name: str, default: Path) -> Path:
    """Return an expanded environment path or the supplied repository default."""

    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


# Repository-local data and intermediate results.
BASE_DIR = _path("RICEMIND_BASE_DIR", REPO_ROOT)
PUBTATOR_DIR = _path("RICEMIND_PUBTATOR_DIR", BASE_DIR / "RICE-pubtator-dir")
SENTENCE_DIR = _path("RICEMIND_SENTENCE_DIR", BASE_DIR / "rice_sentences")
RESULTS_DIR = _path("RICEMIND_RESULTS_DIR", BASE_DIR / "results")
OGER_INPUT_DIR = _path("RICEMIND_OGER_INPUT_DIR", RESULTS_DIR / "oger_input")
OGER_OUTPUT_DIR = _path("RICEMIND_OGER_OUTPUT_DIR", RESULTS_DIR / "oger")
OGER_RESULT_DIR = _path("RICEMIND_OGER_RESULT_DIR", OGER_OUTPUT_DIR)
SCISPACY_OUTPUT_ROOT = _path(
    "RICEMIND_SCISPACY_OUTPUT_ROOT", RESULTS_DIR / "scispacy"
)
PHRASE_OUTPUT_ROOT = _path(
    "RICEMIND_PHRASE_OUTPUT_ROOT", RESULTS_DIR / "phrase"
)
MULTI_ENTITY_OUTPUT = _path(
    "RICEMIND_MULTI_ENTITY_OUTPUT",
    RESULTS_DIR / "multi_entity_sentences_1985-2025.jsonl",
)
KEYWORD_OUTPUT = _path(
    "RICEMIND_KEYWORD_OUTPUT",
    RESULTS_DIR / "keyword_filtered_rice_sentences.jsonl",
)

# Reference data used by later dataset/GTA stages.  These defaults are
# repository-relative; set the variables if the large reference collections
# are stored outside the checkout.
STANDARD_GENE_DIR = _path("RICEMIND_STANDARD_GENE_DIR", BASE_DIR / "standard_gene")
SEQUENCE_DATA_DIR = _path("RICEMIND_SEQUENCE_DATA_DIR", BASE_DIR / "sequence_data")
DATA_DIR = _path("RICEMIND_DATA_DIR", BASE_DIR / "data" / "data_on_server" / "RiceMind")
GTA_DIR = _path("RICEMIND_GTA_DIR", BASE_DIR / "GTA")
GTA_DATA_DIR = _path("RICEMIND_GTA_DATA_DIR", GTA_DIR / "gta")
GTA_OTHER_DB_DIR = _path("RICEMIND_GTA_OTHER_DB_DIR", GTA_DIR / "Other_databases")
SUPP_DICT_DIR = _path(
    "RICEMIND_SUPP_DICT_DIR", BASE_DIR / "dict-dir" / "oger" / "genes"
)

# External NLP dependencies.  These are repository-relative placeholders;
# set the variables to the actual locations on the server before running.

def _detect_oger_package() -> str:
    """Use the active Python environment when OGER is already installed."""

    configured = os.environ.get("RICEMIND_OGER_PACKAGE")
    if configured:
        return configured
    spec = importlib.util.find_spec("oger")
    if spec and spec.submodule_search_locations:
        return str(next(iter(spec.submodule_search_locations)))
    return str(BASE_DIR / "third_party" / "oger")


OGER_PACKAGE = _detect_oger_package()
OGER_TERMLIST = _path(
    "RICEMIND_OGER_TERMLIST",
    BASE_DIR / "OGER++" / "self-built_terms_cleaned_python_10001-end.tsv",
)
SCISPACY_MODEL = _path(
    "RICEMIND_SCISPACY_MODEL",
    BASE_DIR / "third_party" / "en_core_sci_scibert-0.5.4",
)

DICT_DIR = _path("RICEMIND_DICT_DIR", BASE_DIR / "dict-dir")
OGER_DICT_DIR = _path(
    "RICEMIND_OGER_DICT_DIR", DICT_DIR / "oger"
)
ANNOTATION_DICT_DIR = _path("RICEMIND_ANNOTATION_DICT_DIR", DICT_DIR / "annotation")
FILTER_DICT_DIR = _path("RICEMIND_FILTER_DICT_DIR", DICT_DIR / "filtering")
NOISE_BLACKLIST_DIR = _path(
    "RICEMIND_NOISE_BLACKLIST_DIR", FILTER_DICT_DIR / "blacklists"
)
NOISE_BLACKLIST_FILE = _path(
    "RICEMIND_NOISE_BLACKLIST_FILE", FILTER_DICT_DIR / "noise_blacklist.tsv"
)
CLEANED_OUTPUT_ROOT = _path(
    "RICEMIND_CLEANED_OUTPUT_ROOT", RESULTS_DIR / "cleaned"
)
DICT_PATHS = {
    "co": _path("RICEMIND_CO_DICT", ANNOTATION_DICT_DIR / "co-dict.tsv"),
    "go": _path("RICEMIND_GO_DICT", ANNOTATION_DICT_DIR / "go-dict.tsv"),
    "to": _path("RICEMIND_TO_DICT", ANNOTATION_DICT_DIR / "to-dict.tsv"),
    "rto": _path("RICEMIND_RTO_DICT", ANNOTATION_DICT_DIR / "rto-dict.tsv"),
    "variety": _path("RICEMIND_VARIETY_DICT", ANNOTATION_DICT_DIR / "variety-dict.tsv"),
}


def show() -> None:
    """Print the paths most users need to verify on a new server."""

    for name in (
        "REPO_ROOT",
        "BASE_DIR",
        "PUBTATOR_DIR",
        "SENTENCE_DIR",
        "RESULTS_DIR",
        "OGER_INPUT_DIR",
        "OGER_OUTPUT_DIR",
        "SCISPACY_OUTPUT_ROOT",
        "PHRASE_OUTPUT_ROOT",
        "DICT_DIR",
        "FILTER_DICT_DIR",
        "NOISE_BLACKLIST_DIR",
        "NOISE_BLACKLIST_FILE",
        "CLEANED_OUTPUT_ROOT",
        "STANDARD_GENE_DIR",
        "SEQUENCE_DATA_DIR",
        "DATA_DIR",
        "GTA_DIR",
        "OGER_DICT_DIR",
        "SCISPACY_MODEL",
    ):
        print(f"{name}={globals()[name]}")
    print(f"OGER_PACKAGE={OGER_PACKAGE}")
    print(f"OGER_TERMLIST={OGER_TERMLIST}")
    for name, path in DICT_PATHS.items():
        print(f"DICT_{name.upper()}={path}")


if __name__ == "__main__":
    show()
