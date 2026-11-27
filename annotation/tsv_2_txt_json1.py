# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md
"""Backward-compatible entry point for :mod:`tsv_2_txt_json`.

The old copy contained a stale hard-coded server path and called a function
that was not defined in the file.  Keep the filename for existing commands,
but use the maintained converter and its central path configuration.
"""

from tsv_2_txt_json import main


if __name__ == "__main__":
    main()
