#!/usr/bin/env python
"""Run-data-managers is a tool for provisioning data on a galaxy instance.

Run-data-managers has the ability to run multiple data managers that are interdependent.
When a reference genome is needed for bwa-mem for example, Run-data-managers
can first run a data manager to fetch the fasta file and run
another data manager that indexes the fasta file for bwa-mem.
This functionality depends on the "watch_tool_data_dir" setting in galaxy.ini to be True.
Also, if a new data manager is installed, galaxy needs to be restarted in order for it's tool_data_dir to be watched.

Run-data-managers needs a yaml that specifies what data managers are run and with which settings.
Example files can be found `here <https://github.com/galaxyproject/ephemeris/blob/master/tests/run_data_managers.yaml.sample>`_,
`here <https://github.com/galaxyproject/ephemeris/blob/master/tests/run_data_managers.yaml.sample.advanced>`_,
and `here <https://github.com/galaxyproject/ephemeris/blob/master/tests/run_data_managers.yaml.test>`_.

By default run-data-managers skips entries in the yaml file that have already been run.
It checks it in the following way:

  * If the data manager has input variables "name" or "sequence_name" it will check if the "name" column in the data table already has this entry.
    "name" will take precedence over "sequence_name".
  * If the data manager has input variables "value", "sequence_id" or 'dbkey' it will check if the "value"
    column in the data table already has this entry.
    Value takes precedence over sequence_id which takes precedence over dbkey.
  * If none of the above input variables are specified the data manager will always run.
"""
import argparse
import json
import logging
import time
from collections import namedtuple

from bioblend.galaxy.tool_data import ToolDataClient
from bioblend.galaxy.tools import ToolClient
from jinja2 import Template

from . import get_galaxy_connection
from . import load_yaml_file
from .common_parser import get_common_args
from .ephemeris_log import disable_external_library_logging, setup_global_logger

DEFAULT_URL = "http://localhost"
DEFAULT_SOURCE_TABLES = ["all_fasta"]


def wait(gi, job_list, log):
    """
        Waits until all jobs in a list are finished or failed.
        It will check the state of the created datasets every 30s.
        It will return a tuple: ( finished_jobs, failed_jobs )
    """

    failed_jobs = []
    successful_jobs = []

    # Empty list returns false and stops the loop.
    while bool(job_list):
        finished_jobs = []
        for job in job_list:
            job_hid = job['outputs'][0]['hid']
            # check if the output of the running job is either in 'ok' or 'error' state
            state = gi.datasets.show_dataset(job['outputs'][0]['id'])['state']
            if state == 'ok':
                log.info('Job %i finished with state %s.' % (job_hid, state))
                successful_jobs.append(job)
                finished_jobs.append(job)
            if state == 'error':
                log.error('Job %i finished with state %s.' % (job_hid, state))
                job_id = job['jobs'][0]['id']
                job_details = gi.jobs.show_job(job_id, full_details=True)
                log.error(
                    "Job {job_hid}: Tool '{tool_id}' finished with exit code: {exit_code}. Stderr: {stderr}".format(
                        job_hid=job_hid,
                        **job_details
                    ))
                log.debug("Job {job_hid}: Tool '{tool_id}' stdout: {stdout}".format(
                    job_hid=job_hid,
                    **job_details
                ))
                failed_jobs.append(job)
                finished_jobs.append(job)
            else:
                log.debug('Job %i still running.' % job_hid)
        # Remove finished jobs from job_list.
        for finished_job in finished_jobs:
            job_list.remove(finished_job)
        # only sleep if job_list is not empty yet.
        if bool(job_list):
            time.sleep(30)
    return successful_jobs, failed_jobs


def get_first_valid_entry(input_dict, key_list):
    """Iterates over key_list and returns the value of the first key that exists in the dictionary. Or returns None"""
    for key in key_list:
        if key in input_dict:
            return input_dict.get(key)
    return None


class DataManagers:
    def __init__(self, galaxy_instance, configuration):
        """
        :param galaxy_instance: A GalaxyInstance object (import from bioblend.galaxy)
        :param configuration: A dictionary. Examples in the ephemeris documentation.
        """
        self.gi = galaxy_instance
        self.config = configuration
        self.tool_data_client = ToolDataClient(self.gi)
        self.tool_client = ToolClient(self.gi)
        self.possible_name_keys = ['name', 'sequence_name']  # In order of importance!
        self.possible_value_keys = ['value', 'sequence_id', 'dbkey']  # In order of importance!
        self.data_managers = self.config.get('data_managers')
        self.genomes = self.config.get('genomes', '')
        self.source_tables = DEFAULT_SOURCE_TABLES
        self.fetch_jobs = []
        self.skipped_fetch_jobs = []
        self.index_jobs = []
        self.skipped_index_jobs = []

    def initiate_job_lists(self):
        """
        Determines which data managers should be run to populate the data tables.
        Distinguishes between fetch jobs (download files) and index jobs.
        :return: populate self.fetch_jobs, self.skipped_fetch_jobs, self.index_jobs and self.skipped_index_jobs
        """
        self.fetch_jobs = []
        self.skipped_fetch_jobs = []
        self.index_jobs = []
        self.skipped_index_jobs = []
        for dm in self.data_managers:
            jobs, skipped_jobs = self.get_dm_jobs(dm)
            if self.dm_is_fetcher(dm):
                self.fetch_jobs.extend(jobs)
                self.skipped_fetch_jobs.extend(skipped_jobs)
            else:
                self.index_jobs.extend(jobs)
                self.skipped_index_jobs.extend(skipped_jobs)

    def get_dm_jobs(self, dm):
        """Gets the job entries for a single dm. Puts entries that already present in skipped_job_list.
        :returns job_list, skipped_job_list"""
        job_list = []
        skipped_job_list = []
        items = self.parse_items(dm.get('items', ['']))
        for item in items:
            dm_id = dm['id']
            params = dm['params']
            inputs = dict()
            # Iterate over all parameters, replace occurences of {{item}} with the current processing item
            # and create the tool_inputs dict for running the data manager job
            for param in params:
                key, value = list(param.items())[0]
                value_template = Template(value)
                value = value_template.render(item=item)
                inputs.update({key: value})

            job = dict(tool_id=dm_id, inputs=inputs)

            data_tables = dm.get('data_table_reload', [])
            if self.input_entries_exist_in_data_tables(data_tables, inputs):
                skipped_job_list.append(job)
            else:
                job_list.append(job)
        return job_list, skipped_job_list

    def dm_is_fetcher(self, dm):
        """Checks whether the data manager fetches a sequence instead of indexing.
        This is based on the source table.
        :returns True if dm is a fetcher. False if it is not."""
        data_tables = dm.get('data_table_reload', [])
        for data_table in data_tables:
            if data_table in self.source_tables:
                return True
        return False

    def data_table_entry_exists(self, data_table_name, entry, column='value'):
        """Checks whether an entry exists in the a specified column in the data_table."""
        try:
            data_table_content = self.tool_data_client.show_data_table(data_table_name)
        except Exception:
            raise Exception('Table "%s" does not exist' % data_table_name)

        try:
            column_index = data_table_content.get('columns').index(column)
        except IndexError:
            raise IndexError('Column "%s" does not exist in %s' % (column, data_table_name))

        for field in data_table_content.get('fields'):
            if field[column_index] == entry:
                return True
        return False

    def input_entries_exist_in_data_tables(self, data_tables, input_dict):
        """Checks whether name and value entries from the input are already present in the data tables.
        If an entry is missing in of the tables, this function returns False"""
        value_entry = get_first_valid_entry(input_dict, self.possible_value_keys)
        name_entry = get_first_valid_entry(input_dict, self.possible_name_keys)

        # Return False if name and value entries are both None
        if not value_entry and not name_entry:
            return False

        # Check every data table for existence of name and value
        # Return False as soon as entry is not present
        for data_table in data_tables:
            if value_entry:
                if not self.data_table_entry_exists(data_table, value_entry, column='value'):
                    return False
            if name_entry:
                if not self.data_table_entry_exists(data_table, name_entry, column='name'):
                    return False
        # If all checks are passed the entries are present in the database tables.
        return True

    def parse_items(self, items):
        """
        Parses items with jinja2.
        :param items: the items to be parsed
        :return: the parsed items
        """
        if bool(self.genomes):
            items_template = Template(json.dumps(items))
            rendered_items = items_template.render(genomes=json.dumps(self.genomes))
            # Remove trailing " if present
            rendered_items = rendered_items.strip('"')
            items = json.loads(rendered_items)
        return items

    def run(self, log=None, ignore_errors=False, overwrite=False):
        """
        Runs the data managers.
        :param log: The log to be used.
        :param ignore_errors: Ignore erroring data_managers. Continue regardless.
        :param overwrite: Overwrite existing entries in data tables
        """
        self.initiate_job_lists()
        all_succesful_jobs = []
        all_failed_jobs = []
        all_skipped_jobs = []

        if not log:
            log = logging.getLogger()

        def run_jobs(jobs, skipped_jobs):
            job_list = []
            for skipped_job in skipped_jobs:
                if overwrite:
                    log.info('%s already run for %s. Entry will be overwritten.' %
                             (skipped_job["tool_id"], skipped_job["inputs"]))
                    jobs.append(skipped_job)
                else:
                    log.info('%s already run for %s. Skipping.' % (skipped_job["tool_id"], skipped_job["inputs"]))
                    all_skipped_jobs.append(skipped_job)
            for job in jobs:
                started_job = self.tool_client.run_tool(history_id=None, tool_id=job["tool_id"],
                                                        tool_inputs=job["inputs"])
                log.info('Dispatched job %i. Running DM: "%s" with parameters: %s' %
                         (started_job['outputs'][0]['hid'], job["tool_id"], job["inputs"]))
                job_list.append(started_job)

            successful_jobs, failed_jobs = wait(self.gi, job_list, log)
            if failed_jobs:
                if not ignore_errors:
                    log.error('Not all jobs successful! aborting...')
                    raise RuntimeError('Not all jobs successful! aborting...')
                else:
                    log.warning('Not all jobs successful! ignoring...')
            all_succesful_jobs.extend(successful_jobs)
            all_failed_jobs.extend(failed_jobs)

        log.info("Running data managers that populate the following source data tables: %s" % self.source_tables)
        run_jobs(self.fetch_jobs, self.skipped_fetch_jobs)
        log.info("Running data managers that index sequences.")
        run_jobs(self.index_jobs, self.skipped_index_jobs)

        log.info('Finished running data managers. Results:')
        log.info('Successful jobs: %i ' % len(all_succesful_jobs))
        log.info('Skipped jobs: %i ' % len(all_skipped_jobs))
        log.info('Failed jobs: %i ' % len(all_failed_jobs))
        InstallResults = namedtuple("InstallResults", ["successful_jobs", "failed_jobs", "skipped_jobs"])
        return InstallResults(successful_jobs=all_succesful_jobs, failed_jobs=all_failed_jobs,
                              skipped_jobs=all_skipped_jobs)


def _parser():
    """returns the parser object."""
    parent = get_common_args(log_file=True)

    parser = argparse.ArgumentParser(
        parents=[parent],
        description='Running Galaxy data managers in a defined order with defined parameters.'
                    "'watch_tool_data_dir' in galaxy config should be set to true.'")
    parser.add_argument("--config", required=True,
                        help="Path to the YAML config file with the list of data managers and data to install.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Disables checking whether the item already exists in the tool data table.")
    parser.add_argument("--ignore_errors", action="store_true",
                        help="Do not stop running when jobs have failed.")
    return parser


def main():
    disable_external_library_logging()
    parser = _parser()
    args = parser.parse_args()
    log = setup_global_logger(name=__name__, log_file=args.log_file)
    if args.verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    gi = get_galaxy_connection(args, file=args.config, log=log, login_required=True)
    config = load_yaml_file(args.config)
    data_managers = DataManagers(gi, config)
    data_managers.run(log, args.ignore_errors, args.overwrite)


if __name__ == '__main__':
    main()
