#!/usr/bin/env python3
# Modified for the independent RiceMind engineering adaptation.
# Upstream: https://github.com/muhaha2/RiceMind
# Changes: docs/CHANGES_FROM_UPSTREAM.md

import sys
import shlex
import logging
import argparse
import tempfile
from os.path import join, dirname, realpath, abspath
import os
from datetime import datetime

# -----------------------------
# OGER Python path configuration
# -----------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import OGER_OUTPUT_DIR, OGER_PACKAGE

oger_path = OGER_PACKAGE
sys.path.insert(0, os.path.dirname(oger_path))

from oger.ctrl.run import run
from oger.ctrl import parameters

# -----------------------------
# GLOBAL VARIABLES
# -----------------------------
CACHE = tempfile.TemporaryDirectory()
OUTPUT = str(OGER_OUTPUT_DIR)
testlogger = logging.getLogger("test")

# -----------------------------
# MAIN ENTRY POINT
# -----------------------------
def main():
    """
    Run OGER processing for txt.json files with support for multiple term lists.
    """
    ap = argparse.ArgumentParser(description="Process txt.json files with OGER using one or multiple term lists.")
    ap.add_argument(
        "-i", "--input",
        required=True,
        metavar="PATH",
        help="Path to the input txt.json file."
    )
    ap.add_argument(
        "-t", "--termlist",
        required=True,
        nargs="+",
        metavar="PATH",
        help="Path(s) to term list file(s). You can specify multiple paths separated by spaces."
    )
    ap.add_argument(
        "-o", "--output",
        default=OUTPUT,
        metavar="PATH",
        help="Directory for output files (default: %(default)s)"
    )
    ap.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed progress info on STDERR."
    )
    args = ap.parse_args()

    process_txtjson(**vars(args))

# -----------------------------
# MAIN PROCESSING FUNCTION
# -----------------------------
def process_txtjson(input, termlist, output, verbose):
    """
    Process a txt.json input file with OGER using multiple term lists.
    """
    # Setup output directory and logging
    outputdir = join(output, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(outputdir, exist_ok=True)
    setup_logging(verbose, outputdir)

    try:
        testlogger.info("Processing txt.json file: %s", input)
        testlogger.info("Using term lists: %s", ", ".join(termlist))
        txt_json(outputdir, input, termlist)
        testlogger.info("Processing completed successfully.")
    except Exception as e:
        testlogger.error("Processing failed: %s", e)
        logging.exception("Stack trace:")
        sys.exit(1)

# -----------------------------
# LOGGING CONFIGURATION
# -----------------------------
def setup_logging(verbose, outputdir):
    """
    Configure loggers for file and console output.
    """
    logfile = logging.FileHandler(join(outputdir, "processing.log"))
    logfile.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    stderr = logging.StreamHandler()
    stderr.setFormatter(logging.Formatter("%(message)s"))

    rootlogger = logging.getLogger()
    rootlogger.setLevel(logging.INFO)
    rootlogger.addHandler(logfile)

    testlogger.setLevel(logging.INFO)

    if verbose:
        rootlogger.addHandler(stderr)
    else:
        testlogger.addHandler(stderr)

# -----------------------------
# ARGUMENT CONSTRUCTION
# -----------------------------
def make_arguments(input_file, output_dir, export_format, termlists):
    """
    Generate the argument string to call the OGER pipeline with multiple term lists.
    """
    # Construct dynamic termlist arguments
    termlist_args = []
    for i, path in enumerate(termlists, start=1):
        termlist_args.append(f"-c termlist{i}_path {path}")
    termlist_block = " ".join(termlist_args)

    arguments = f"""
        -t glob
        -m document
        -f txt_json
        -i {os.path.dirname(input_file)}
        -o {output_dir}
        {termlist_block}
        -c termlist_cache {CACHE.name}
        -c termlist_skip_header true
        -e {export_format}
        -j 4
        -- {os.path.basename(input_file)}
        """
    return arguments

# -----------------------------
# PIPELINE EXECUTION
# -----------------------------
def run_with_arguments(arguments_string):
    """
    Run OGER with parsed arguments.
    """
    argument_list = shlex.split(arguments_string.strip())
    arguments = parameters.parse_cmdline(argument_list)
    run(**arguments)

# -----------------------------
# FORMAT PROCESSING
# -----------------------------
def txt_json(outputdir, input_file, termlists):
    """
    Process txt.json format with OGER and export results in multiple output formats.
    """
    output_formats = ["bioc_json", "pubtator"]

    for output_format in output_formats:
        testlogger.info("-> Exporting to %s", output_format)
        output = join(outputdir, output_format)
        os.makedirs(output, exist_ok=True)
        arguments = make_arguments(input_file=input_file, output_dir=output, export_format=output_format, termlists=termlists)
        run_with_arguments(arguments)

# -----------------------------
# EXECUTION
# -----------------------------
if __name__ == "__main__":
    main()
