#!/usr/bin/env python

import argparse


def get_common_args(login_required=True):

    parser = argparse.ArgumentParser(add_help=False)
    general_group = parser.add_argument_group('Galaxy connection')
    general_group.add_argument("-v", "--verbose", help="Increase output verbosity.", action="store_true")

    con_group = parser.add_argument_group('Galaxy connection')
    con_group.add_argument("-g", "--galaxy",
                           help="Target Galaxy instance URL/IP address",
                           default="http://localhost:8080")

    if login_required:
        con_group.add_argument("-u", "--user",
                               help="Galaxy user name")
        con_group.add_argument("-p", "--password",
                               help="Password for the Galaxy user")
        con_group.add_argument("-a", "--api_key",
                               dest="api_key",
                               help="Galaxy admin user API key (required if not defined in the tools list file)")
    return parser
