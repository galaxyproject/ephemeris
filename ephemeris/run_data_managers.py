#!/usr/bin/env python
'''Run-data-managers is a tool for provisioning data on a galaxy instance.

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
* If the data manager has input variables "value", "sequence_id" or 'dbkey' it will check if
  the "value" column in the data table already has this entry.
  Value takes precedence over sequence_id which takes precedence over dbkey.
* If none of the above input variables are specified the data manager will always run.
'''
import argparse
import json
import logging
import time

import yaml
from bioblend.galaxy.tool_data import ToolDataClient
from jinja2 import Template

from . import get_galaxy_connection
from .common_parser import get_common_args
from .ephemeris_log import disable_external_library_logging, setup_global_logger


DEFAULT_URL = "http://localhost"


def wait(gi, job_list):
    """
        Waits until a data_manager is finished or failed.
        It will check the state of the created datasets every 30s.
        It will return a tuple: ( finished_jobs, failed_jobs )
    """

    failed_jobs = []
    successful_jobs = []

    # Empty list returns false and stops the loop.
    while bool(job_list):
        finished_jobs = []
        for job in job_list:
            value = job['outputs']
            job_id = job['outputs'][0]['hid']
            # check if the output of the running job is either in 'ok' or 'error' state
            state = gi.datasets.show_dataset(value[0]['id'])['state']
            if state == 'ok':
                log.info('Job %i finished with state %s.' % (job_id, state))
                successful_jobs.append(job)
                finished_jobs.append(job)
            if state == 'error':
                log.error('Job %i finished with state %s.' % (job_id, state))
                failed_jobs.append(job)
                finished_jobs.append(job)
            else:
                log.debug('Job %i still running.' % job_id)
        # Remove finished jobs from job_list.
        for finished_job in finished_jobs:
            job_list.remove(finished_job)
        # only sleep if job_list is not empty yet.
        if bool(job_list):
            time.sleep(30)
    return successful_jobs, failed_jobs


def data_table_entry_exists(tool_data_client, data_table_name, entry, column='value'):
    '''Checks whether an entry exists in the a specified column in the data_table.'''
    try:
        data_table_content = tool_data_client.show_data_table(data_table_name)
    except Exception:
        raise Exception('Table "%s" does not exist' % (data_table_name))

    try:
        column_index = data_table_content.get('columns').index(column)
    except IndexError:
        raise IndexError('Column "%s" does not exist in %s' % (column, data_table_name))

    for field in data_table_content.get('fields'):
        if field[column_index] == entry:
            return True
    return False


def get_name_from_inputs(input_dict):
    '''Returns the value that will most likely be recorded in the "name" column of the datatable. Or returns False'''
    possible_keys = ['name', 'sequence_name']  # In order of importance!
    for key in possible_keys:
        if key in input_dict:
            return input_dict.get(key)
    return False


def get_value_from_inputs(input_dict):
    '''Returns the value that will most likely be recorded in the "value" column of the datatable. Or returns False'''
    possible_keys = ['value', 'sequence_id', 'dbkey']  # In order of importance!
    for key in possible_keys:
        if key in input_dict:
            return input_dict.get(key)
    return False


def input_entries_exist_in_data_tables(tool_data_client, data_tables, input_dict):
    '''Checks whether name and value entries from the input are already present in the data tables.
    If an entry is missing in of the tables, this function returns False'''
    value_entry = get_value_from_inputs(input_dict)
    name_entry = get_name_from_inputs(input_dict)

    # Return False if name and value entries are both False
    if not value_entry and not name_entry:
        return False

    # Check every data table for existance of name and value
    # Return False as soon as entry is not present
    for data_table in data_tables:
        if value_entry:
            if not data_table_entry_exists(tool_data_client, data_table, value_entry, column='value'):
                return False
        if name_entry:
            if not data_table_entry_exists(tool_data_client, data_table, name_entry, column='name'):
                return False
    # If all checks are passed the entries are present in the database tables.
    return True


def parse_items(items, genomes):
    if bool(genomes):
        items_template = Template(json.dumps(items))
        rendered_items = items_template.render(genomes=json.dumps(genomes))
        # Remove trailing " if present
        rendered_items = rendered_items.strip('"')
        items = json.loads(rendered_items)
    return items


def run_dm(args):
    args.galaxy = args.galaxy or DEFAULT_URL
    gi = get_galaxy_connection(args, log=log)
    # should test valid connection
    # The following should throw a ConnectionError when invalid API key or password
    genomes = gi.genomes.get_genomes()  # Does not get genomes but preconfigured dbkeys
    log.info('Number of possible dbkeys: %s' % str(len(genomes)))

    tool_data_client = ToolDataClient(gi)

    number_skipped_jobs = 0
    all_failed_jobs = []
    all_successful_jobs = []

    conf = yaml.load(open(args.config))
    genomes = conf.get('genomes', '')
    for dm in conf.get('data_managers'):
        items = parse_items(dm.get('items', ['']), genomes)
        job_list = []
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

            data_tables = dm.get('data_table_reload', [])
            # Only run if not run before.
            if input_entries_exist_in_data_tables(tool_data_client, data_tables, inputs) and not args.overwrite:
                log.info('%s already run for %s' % (dm_id, inputs))
                number_skipped_jobs += 1
            else:
                # run the DM-job
                job = gi.tools.run_tool(history_id=None, tool_id=dm_id, tool_inputs=inputs)
                log.info('Dispatched job %i. Running DM: "%s" with parameters: %s' % (job['outputs'][0]['hid'], dm_id, inputs))
                job_list.append(job)
        successful_jobs, failed_jobs = wait(gi, job_list)
        if failed_jobs:
            if not args.ignore_errors:
                raise Exception('Not all jobs successful! aborting...')
                break
            else:
                log.error('Not all jobs successful! ignoring...')
        all_successful_jobs += successful_jobs
        all_failed_jobs += failed_jobs
    job_summary = dict()
    job_summary['successful_jobs'] = len(all_successful_jobs)
    job_summary['failed_jobs'] = len(all_failed_jobs)
    job_summary['skipped_jobs'] = number_skipped_jobs
    return job_summary


def _parser():
    '''returns the parser object.'''
    parent = get_common_args()

    parser = argparse.ArgumentParser(
        parents=[parent],
        description='Running Galaxy data managers in a defined order with defined parameters.')
    parser.add_argument("--config", required=True,
                        help="Path to the YAML config file with the list of data managers and data to install.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Disables checking whether the item already exists in the tool data table.")
    parser.add_argument("--ignore_errors", action="store_true",
                        help="Do not stop running when jobs have failed.")
    return parser


def main():
    global log
    disable_external_library_logging()
    log = setup_global_logger(name=__name__, log_file='/tmp/galaxy_data_manager_install.log')
    parser = _parser()
    args = parser.parse_args()
    if args.verbose:

        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    log.info("Running data managers...")
    job_summary = run_dm(args)
    log.info('Finished running data managers. Results:')
    log.info('Successful jobs: %i ' % job_summary['successful_jobs'])
    log.info('Skipped jobs: %i ' % job_summary['skipped_jobs'])
    log.info('Failed jobs: %i ' % job_summary['failed_jobs'])


if __name__ == '__main__':
    main()
