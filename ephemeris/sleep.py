#!/usr/bin/env python
import sys
import time

from argparse import ArgumentParser

import requests

from .common_parser import get_common_args


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parent = get_common_args(login_required=False)
    parser = ArgumentParser(parents=[parent], usage="usage: python %(prog)s <options>",
                            description="Script to sleep and wait for Galaxy to be alive.")
    parser.add_argument("--timeout",
                        default=0, type=int,
                        help="Galaxy startup timeout in seconds. The default value of 0 waits forever")
    return parser.parse_args()


def main():
    """
    Main function
    """
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
