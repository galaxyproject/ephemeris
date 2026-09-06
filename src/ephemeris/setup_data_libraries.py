#!/usr/bin/env python
"""Tool to setup data libraries on a galaxy instance."""

import argparse
import logging as log
import os
import sys
import time
from urllib.parse import urlparse

import yaml
from bioblend import galaxy

from .common_parser import (
    DEFAULT_JOB_SLEEP,
    get_common_args,
    HideUnderscoresHelpFormatter,
)

HISTORY_NAME = "data library upload (automatic)"


def _basename(url):
    path = urlparse(url).path
    return os.path.basename(path) or url


def _desired_name(item):
    return item.get("name") or _basename(item["url"])


def _hash_fields(item):
    """Extract hash fields from the YAML item for the fetch payload.

    Accepts lowercase keys (`md5`, `sha256`, etc.) and normalizes them to
    the case expected by Galaxy's fetch API (`MD5`, `SHA-256`, etc.).
    """
    out = {}
    hash_keys = {
        "md5": "MD5",
        "sha1": "SHA-1",
        "sha-1": "SHA-1",
        "sha256": "SHA-256",
        "sha-256": "SHA-256",
        "sha512": "SHA-512",
        "sha-512": "SHA-512",
    }
    for key, value in item.items():
        canonical_key = hash_keys.get(key.lower())
        if canonical_key:
            out[canonical_key] = str(value)
    if "hashes" in item:
        out["hashes"] = item["hashes"]
    return out


def _strip_folder_prefix(folder_id):
    """Galaxy's fetch API expects library_folder_id WITHOUT the 'F' prefix."""
    return folder_id.removeprefix("F")


def _existing_dataset_names(gi, lib_id, folder_path, cache):
    """Return {dataset_name: dataset_id} for non-deleted files in the folder.

    The full library contents are fetched once and cached for the lifetime of the process.
    """
    if lib_id not in cache:
        names_by_folder = {}
        try:
            contents = gi.libraries.show_library(lib_id, contents=True)
            if isinstance(contents, list):
                for item in contents:
                    if item.get("type") == "file" and not item.get("deleted", False):
                        full_name = item.get("name", "")
                        # name is like "/Small Files/README.txt"
                        parts = full_name.rsplit("/", 1)
                        if len(parts) == 2:
                            fpath, ds_name = parts
                            fpath = fpath or "/"
                            names_by_folder.setdefault(fpath, {})[ds_name] = item["id"]
        except Exception:
            pass
        cache[lib_id] = names_by_folder
    return cache[lib_id].setdefault(folder_path, {})


def _fetch_upload(gi, history_id, folder_id, items, deferred=False):
    """Upload a list of file items into a library folder via /api/tools/fetch.

    Uses the modern fetch API with ``library_folder`` destinations, which
    supports setting the dataset ``name`` at upload time and hashsum
    verification (MD5, SHA-256, etc.).
    """
    elements = []
    for item in items:
        if item.get("src", "url") != "url":
            raise Exception("Only URL source items are supported.")
        elem = {
            "src": "url",
            "url": item["url"],
            "name": _desired_name(item),
            "ext": item.get("ext") or "auto",
        }
        if item.get("info"):
            elem["info"] = item["info"]
        if item.get("dbkey"):
            elem["dbkey"] = item["dbkey"]
        if deferred or item.get("deferred"):
            elem["deferred"] = True
        elem.update(_hash_fields(item))
        elements.append(elem)

    payload = {
        "history_id": history_id,
        "targets": [
            {
                "destination": {
                    "type": "library_folder",
                    "library_folder_id": _strip_folder_prefix(folder_id),
                },
                "elements": elements,
            }
        ],
    }

    try:
        result = gi.tools._post(payload=payload, id="fetch")
    except Exception as exc:
        body = str(exc)
        # If the error is about an unknown extension, retry with "auto".
        if "unknown" in body.lower() and "extension" in body.lower():
            log.warning("Unknown extension(s); retrying with ext='auto'")
            for elem in elements:
                elem["ext"] = "auto"
            result = gi.tools._post(payload=payload, id="fetch")
        else:
            log.error("Fetch API error: %s", body[:500])
            raise
    return result


def _get_or_create_history(gi):
    """Get or create a named history for library uploads.

    The fetch API requires a history_id.
    We reuse a single history across runs. No datasets are stored in it (they go to the library).
    """
    existing = gi.histories.get_histories(name=HISTORY_NAME)
    if existing:
        return existing[0]["id"]
    return gi.histories.create_history(name=HISTORY_NAME)["id"]


def _set_public_permissions(gi, lib_id, folder_id=None):
    """Set library and optionally folder permissions to public.

    When datasets are uploaded to a library folder via the fetch API, they
    inherit the folder's permissions. By setting LIBRARY_ACCESS_in to [],
    the library becomes accessible to everyone.
    """
    gi.libraries._post({"LIBRARY_ACCESS_in": []}, url=f"{gi.libraries._make_url(lib_id)}/permissions")
    if folder_id:
        gi.folders._post(
            {"action": "set_permissions", "add_ids[]": []}, url=f"{gi.folders._make_url(folder_id)}/permissions"
        )


def create_library(gi, desc, make_public=False, force_public=False, deferred=False):
    destination = desc["destination"]
    if destination["type"] != "library":
        raise Exception("Only libraries may be created with this script.")
    library_name = destination.get("name")
    library_description = destination.get("description")
    library_synopsis = destination.get("synopsis")

    # Check to see if the library already exists. If it does, do not recreate it.
    # If it doesn't, create it.
    lib_id = None
    print("Library name: " + str(library_name))
    rmt_lib_list = gi.libraries.get_libraries(name=library_name, deleted=False)
    not_deleted_rmt_lib_list = []
    folder_id = None

    if rmt_lib_list:
        for x in rmt_lib_list:
            if not x["deleted"]:
                not_deleted_rmt_lib_list.append(x)
    if not_deleted_rmt_lib_list:
        lib_id = not_deleted_rmt_lib_list[0]["id"]
        print("Library already exists! id: " + str(lib_id))
        folder_id = gi.libraries.show_library(lib_id)["root_folder_id"]
    else:
        lib = gi.libraries.create_library(library_name, library_description, library_synopsis)
        lib_id = lib["id"]
        folder_id = lib["root_folder_id"]

    if make_public:
        _set_public_permissions(gi, lib_id)

    history_id = _get_or_create_history(gi)
    jobs = []
    existing_dataset_cache = {}

    def populate_items(base_folder_id, has_items, parent_path="/"):
        if "items" in has_items:
            item_list = has_items["items"]
            # Skip creating folders for nodes that have no files or sub-folders.
            # Many GTN tutorials have empty data-library.yaml files; we don't want
            # thousands of empty folders in the library.
            if not item_list:
                return None
            name = has_items.get("name")
            description = has_items.get("description")
            gtn_url = has_items.get("gtn_url")
            if gtn_url:
                desc_parts = [description, f"See: {gtn_url}"] if description else [gtn_url]
                description = "\n".join(desc_parts)
            folder_id = base_folder_id
            if name:
                full_path = parent_path.rstrip("/") + "/" + name
                rmt_folder_list = gi.libraries.get_folders(lib_id, name=full_path)
                if rmt_folder_list:
                    folder_id = rmt_folder_list[0]["id"]
                    if force_public:
                        _set_public_permissions(gi, lib_id, folder_id)
                else:
                    folder = gi.libraries.create_folder(lib_id, name, description, base_folder_id=base_folder_id)
                    folder_id = folder[0]["id"]
                    if make_public or force_public:
                        _set_public_permissions(gi, lib_id, folder_id)
                for item in item_list:
                    populate_items(folder_id, item, full_path)
            else:
                for item in item_list:
                    populate_items(folder_id, item, parent_path)
        else:
            desired = _desired_name(has_items)
            url = has_items["url"]
            existing = _existing_dataset_names(gi, lib_id, parent_path, existing_dataset_cache)
            if desired in existing or url in existing:
                url_id = existing.get(url)
                if url_id and desired != url and desired not in existing:
                    try:
                        gi.libraries.update_library_dataset(url_id, name=desired)
                        existing[desired] = url_id
                        existing.pop(url, None)
                        log.info("Renamed legacy dataset %s -> %s", url, desired)
                    except Exception as exc:
                        log.warning("Could not rename %s: %s", url, exc)
                else:
                    log.debug("Skipping existing %r", desired)
                return None
            try:
                job = _fetch_upload(gi, history_id, base_folder_id, [has_items], deferred=deferred)
                jobs.append(job)
                existing[desired] = None
            except Exception:
                log.exception(
                    "Could not upload %s to %s/%s",
                    has_items["url"],
                    lib_id,
                    base_folder_id,
                )
        return None

    populate_items(folder_id, desc, "/")
    return jobs


def setup_data_libraries(gi, data, training=False, make_public=False, force_public=False, deferred=False):
    """
    Load files into a Galaxy data library.

    Uses Galaxy's fetch API (``POST /api/tools/fetch``) with ``library_folder``
    destinations for file uploads.  The fetch API supports setting the dataset
    ``name`` at upload time and hashsum verification (MD5, SHA-256, etc.).
    Existing datasets are looked up by name and skipped, making this idempotent.

    When ``make_public`` is True, library and folder permissions are set to
    public (no role restrictions) for newly created items, making all uploaded
    datasets accessible to everyone.

    When ``force_public`` is True, permissions are also re-set on existing
    folders (useful for fixing permission regressions). Implies ``make_public``.

    When ``deferred`` is True, datasets are uploaded as deferred, they are
    not fetched at upload time but materialized on first use. This is useful
    for fast testing of library layout and titles without downloading all files.
    """

    log.info("Importing data libraries.")

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
        destination["name"] = destination.get("name", "Training Data")
        destination["description"] = destination.get("description", "Data pulled from online archives.")
    else:
        destination["name"] = destination.get("name", "New Data Library")
        destination["description"] = destination.get("description", "")

    normalize_items(library_def)

    if library_def:
        jobs = create_library(gi, library_def, make_public=make_public, force_public=force_public, deferred=deferred)
        job_ids = []
        for job in jobs:
            if "jobs" in job:
                for subjob in job["jobs"]:
                    job_ids.append(subjob["id"])

        jc = galaxy.jobs.JobsClient(gi)
        while True:
            job_states = [jc.get_state(job) in ("ok", "error", "deleted") for job in job_ids]
            log.debug(
                f'Job states: {",".join([f"{job_id}={job_state}" for (job_id, job_state) in zip(job_ids, job_states)])}'
            )

            if all(job_states):
                break
            time.sleep(DEFAULT_JOB_SLEEP)

        log.info("Finished importing test data.")


def _parser():
    """Constructs the parser object"""
    parent = get_common_args()
    parser = argparse.ArgumentParser(
        parents=[parent],
        formatter_class=HideUnderscoresHelpFormatter,
        description="Populate the Galaxy data library with data.",
    )
    parser.add_argument("-i", "--infile", required=True, type=argparse.FileType("r"))
    parser.add_argument(
        "--training",
        default=False,
        action="store_true",
        help="Set defaults that make sense for training data.",
    )
    parser.add_argument(
        "--make-public",
        default=False,
        action="store_true",
        help="Make library, folders, and datasets publicly accessible.",
    )
    parser.add_argument(
        "--force-public",
        default=False,
        action="store_true",
        help="Re-set permissions on all existing folders to public (implies --make-public).",
    )
    parser.add_argument(
        "--deferred",
        default=False,
        action="store_true",
        help="Upload datasets as deferred (materialized on first use, not at upload time).",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.user and args.password:
        gi = galaxy.GalaxyInstance(url=args.galaxy, email=args.user, password=args.password)
    elif args.api_key:
        gi = galaxy.GalaxyInstance(url=args.galaxy, key=args.api_key)
    else:
        sys.exit("Please specify either a valid Galaxy username/password or an API key.")

    if args.verbose:
        log.basicConfig(level=log.DEBUG)

    make_public = args.make_public or args.force_public
    setup_data_libraries(
        gi, args.infile, training=args.training, make_public=make_public,
        force_public=args.force_public, deferred=args.deferred,
    )


if __name__ == "__main__":
    main()
