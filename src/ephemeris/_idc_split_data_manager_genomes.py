#!/usr/bin/env python
"""Helper script for IDC - not yet meant for public consumption.

This script splits genomes.yml into tasks that are meant to be sent to
run_data_managers.py - while excluding data managers executions specified
by genomes.yml that have already been executed and appear in the target
installed data table configuration.
"""
import os

from galaxy.util import safe_makedirs

from ._idc_build import (
    BuildOptions,
    configure_python_for_build,
    RunDataManager,
    TASK_FILE_NAME,
    walk_over_incomplete_runs,
    write_run_data_manager_to_file,
)


def split_genomes(build_options: BuildOptions) -> None:

    def write_task_file(build_id: str, indexer: str, run_data_manager: RunDataManager):
        split_genomes_path = build_options.split_genomes_path
        if not os.path.exists(build_options.split_genomes_path):
            safe_makedirs(split_genomes_path)

        task_file_dir = os.path.join(split_genomes_path, build_id, indexer)
        task_file = os.path.join(task_file_dir, TASK_FILE_NAME)
        write_run_data_manager_to_file(run_data_manager, task_file)

    for build_id, indexer, run_data_manager in walk_over_incomplete_runs(build_options):
        write_task_file(build_id, indexer, run_data_manager)


def main():
    build_options = configure_python_for_build()
    split_genomes(build_options)


if __name__ == "__main__":
    main()
