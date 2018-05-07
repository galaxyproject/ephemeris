#!/usr/bin/env python
'''Tool to setup data libraries on a galaxy instance'''
import argparse
import logging as log
import sys
import time

import yaml
from bioblend import galaxy

from .common_parser import get_common_args


def create_legacy(gi, desc):
    destination = desc["destination"]
    if destination["type"] != "library":
        raise Exception("Only libraries may be created with pre-18.05 Galaxies using this script.")
    library_name = destination.get("name")
    library_description = destination.get("description")
    library_synopsis = destination.get("synopsis")

    lib = gi.libraries.create_library(library_name, library_description, library_synopsis)
    lib_id = lib['id']
    folder_id = None

    def populate_items(base_folder_id, has_items):
        if "items" in has_items:
            name = has_items.get("name")
            folder_id = base_folder_id
            if name:
                folder = gi.libraries.create_folder(lib_id, name, base_folder_id=base_folder_id)
                folder_id = folder[0]["id"]
            for item in has_items["items"]:
                populate_items(folder_id, item)
        else:
            src = has_items["src"]
            if src != "url":
                raise Exception("For pre-18.05 Galaxies only support URLs src items are supported.")

            gi.libraries.upload_file_from_url(
                lib_id,
                has_items['url'],
                folder_id=base_folder_id,
                file_type=has_items['ext']
            )

    populate_items(folder_id, desc)


def create_batch_api(gi, desc):
    hc = galaxy.histories.HistoryClient(gi)
    tc = galaxy.tools.ToolClient(gi)

    history = hc.create_history()
    url = "%s/tools/fetch" % gi.url
    payload = {
        'targets': [desc],
        'history_id': history["id"]
    }
    tc._post(payload=payload, url=url)


def setup_data_libraries(gi, data, training=False, legacy=False):
    """
    Load files into a Galaxy data library.
    By default all test-data tools from all installed tools
    will be linked into a data library.
    """

    log.info("Importing data libraries.")
    jc = galaxy.jobs.JobsClient(gi)
    config = galaxy.config.ConfigClient(gi)
    version = config.get_version()

    if legacy:
        create_func = create_legacy
    else:
        version_major = version.get("version_major", "16.01")
        create_func = create_batch_api if version_major >= "18.05" else create_legacy

    library_def = yaml.safe_load(data)

    def normalize_items(has_items):
        # Synchronize Galaxy batch format with older training material style.
        if "files" in has_items:
            items = has_items.pop("files")
            has_items["items"] = items

        items = has_items.get("items", [])
        for item in items:
            normalize_items(item)
            src = item.get("src")
            url = item.get("url")
            if src is None and url:
                item["src"] = "url"
            if "file_type" in item:
                ext = item.pop("file_type")
                item["ext"] = ext

    # Normalize library definitions to allow older ephemeris style and native Galaxy batch
    # upload formats.
    if "libraries" in library_def:
        # File contains multiple definitions.
        library_def["items"] = library_def.pop("libraries")

    if "destination" not in library_def:
        library_def["destination"] = {"type": "library"}
    destination = library_def["destination"]

    if training:
        destination["name"] = destination.get("name", 'Training Data')
        destination["description"] = destination.get("description", 'Data pulled from online archives.')
    else:
        destination["name"] = destination.get("name", 'New Data Library')
        destination["description"] = destination.get("description", '')

    normalize_items(library_def)

    if library_def:
        create_func(gi, library_def)

        no_break = True
        while True:
            no_break = False
            for job in jc.get_jobs():
                if job['state'] != 'ok':
                    no_break = True
            if not no_break:
                break
            time.sleep(3)

        time.sleep(20)
        log.info("Finished importing test data.")


def _parser():
    '''Constructs the parser object'''
    parent = get_common_args()
    parser = argparse.ArgumentParser(
        parents=[parent],
        description='Populate the Galaxy data library with data.'
    )
    parser.add_argument('-i', '--infile', required=True, type=argparse.FileType('r'))
    parser.add_argument('--training', default=False, action="store_true",
                        help="Set defaults that make sense for training data.")
    parser.add_argument('--legacy', default=False, action="store_true",
                        help="Use legacy APIs even for newer Galaxies that should have a batch upload API enabled.")
    return parser


def main():
    args = _parser().parse_args()
    if args.user and args.password:
        gi = galaxy.GalaxyInstance(url=args.galaxy, email=args.user, password=args.password)
    elif args.api_key:
        gi = galaxy.GalaxyInstance(url=args.galaxy, key=args.api_key)
    else:
        sys.exit('Please specify either a valid Galaxy username/password or an API key.')

    if args.verbose:
        log.basicConfig(level=log.DEBUG)

    setup_data_libraries(gi, args.infile, training=args.training, legacy=args.legacy)


if __name__ == '__main__':
    main()
