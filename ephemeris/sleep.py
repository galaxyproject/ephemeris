#!/usr/bin/env python
import requests
import sys
import time

from argparse import ArgumentParser

from .common_parser import get_common_args
from .shed_install import setup_global_logger, _disable_external_library_logging


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parent = get_common_args(login_required=False)
    parser = ArgumentParser(parents=[parent], usage="usage: python %(prog)s <options>")
    parser.add_argument("--timeout",
                        default=0, type=int,
                        help="Galaxy startup timeout. The default value of 0 waits forever")
    return parser.parse_args()


def main():
    global log
    _disable_external_library_logging()
    log = setup_global_logger(include_file=True)
    options = _parse_cli_options()

    count = 0
    while True:
        try:
            result = requests.get(options.galaxy + '/api/version').json()
            if options.verbose:
                sys.stdout.write("Galaxy Version: %s\n" % result['version_major'])
            break
        except requests.exceptions.ConnectionError as e:
            if options.verbose:
                sys.stdout.write("[%02d] Galaxy not up yet... %s\n" % (count, str(e)[0:100]))
                sys.stdout.flush()
        count += 1

        # If we cannot talk to galaxy and are over the timeout
        if options.timeout != 0 and count > options.timeout:
            sys.stderr.write("Failed to contact Galaxy\n")
            sys.exit(1)

        time.sleep(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
