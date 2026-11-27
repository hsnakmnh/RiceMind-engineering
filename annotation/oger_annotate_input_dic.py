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

# OGER's Python package directory and result paths are defined centrally.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from ricemind_config import OGER_OUTPUT_DIR, OGER_PACKAGE, OGER_TERMLIST

oger_path = OGER_PACKAGE
sys.path.insert(0, os.path.dirname(oger_path))

# ..........
from oger.ctrl.run import run
from oger.ctrl import parameters

#############################
# SETUP AND CONFIGURATION
#############################

# Default termlist path
# OGER term list.  Pass --termlist when a different dictionary is needed.
DEFAULT_TERMLIST = str(OGER_TERMLIST)
CACHE = tempfile.TemporaryDirectory()
OUTPUT = str(OGER_OUTPUT_DIR)

testlogger = logging.getLogger("test")

def main():
    """
    Run txt.json format processing.
    """
    ap = argparse.ArgumentParser(description="Process txt.json format files with OGER")
    ap.add_argument("-i", "--input", required=True, metavar="PATH", help="input txt.json file path")
    ap.add_argument("-o", "--output", default=OUTPUT, metavar="PATH", help="directory for the output (default: %(default)s)")
    ap.add_argument("-t", "--termlist", default=DEFAULT_TERMLIST, metavar="PATH", 
                   help="path to termlist file (default: %(default)s)")
    ap.add_argument("-v", "--verbose", action="store_true", help="include detailed progress info on STDERR")
    args = ap.parse_args()
    process_txtjson(**vars(args))

def process_txtjson(input, output, termlist, verbose):
    """
    Process txt.json format file.
    """
    # Setup logging and output directories
    outputdir = join(output, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(outputdir, exist_ok=True)
    setup_logging(verbose, outputdir)

    try:
        testlogger.info("Processing txt.json file: %s", input)
        testlogger.info("Using termlist: %s", termlist)
        txt_json(outputdir, input, termlist)
        testlogger.info("Processing completed successfully")

    except Exception as e:
        testlogger.error("Processing failed: %s", e)
        logging.exception("Stack trace:")
        sys.exit(1)

def setup_logging(verbose, outputdir):
    """
    Setup logging configuration.
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

def make_arguments(input_file, output_dir, export_format, termlist_path):
    """Generate argument string to call the pipeline with"""
    arguments = """
        -t glob
        -m document
        -f txt_json
        -i {input_dir}
        -o {output}
        -c termlist1_path {termlist}
        -c termlist_cache {cache}
        -c termlist_skip_header true
        -e {export}
        -- {filename}
        """.format(
        input_dir=os.path.dirname(input_file),
        output=output_dir,
        termlist=termlist_path,
        cache=CACHE.name,
        export=export_format,
        filename=os.path.basename(input_file)
    )
    return arguments

def run_with_arguments(arguments_string):
    argument_list = shlex.split(arguments_string.strip())
    arguments = parameters.parse_cmdline(argument_list)
    run(**arguments)

def txt_json(outputdir, input_file, termlist_path):
    """
    Process txt.json format file with various output formats.
    """
    # Define output formats you want to support
    output_formats = ["bioc_json", "pubtator", "tsv", "xml"]

    for output_format in output_formats:
        testlogger.info("-> Exporting to %s", output_format)
        output = join(outputdir, output_format)
        os.makedirs(output, exist_ok=True)
        arguments = make_arguments(input_file=input_file, output_dir=output, 
                                 export_format=output_format, termlist_path=termlist_path)
        run_with_arguments(arguments)

if __name__ == "__main__":
    main()
