#!/usr/bin/env python
'''Run-data-managers is a tool for provisioning data on a galaxy instance.

Run-data-managers has the ability to reload the datatables after a data manager has finished.
It is therefore able to run multiple data managers that are interdependent.
When a reference genome is needed for bwa-mem for example, Run-data-managers
can first run a data manager to fetch the fasta file, reload the data table and run
another data manager that indexes the fasta file for bwa-mem.

Run-data-managers needs a yaml that specifies what data managers are run and with which settings.
An example file can be found `here <https://github.com/galaxyproject/ephemeris/blob/master/tests/run_data_managers.yaml.sample>`_.
By default run-data-managers skips entries in the yaml file that have already been run.
'''
import argparse
import logging as log
import re
import time

import yaml
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.tool_data import ToolDataClient

from .common_parser import get_common_args

DEFAULT_URL = "http://localhost"


def wait(gi, job):
    """
        Waits until a data_manager is finished or failed.
        It will check the state of the created datasets every 30s.
    """
    while True:
        value = job['outputs']
        # check if the output of the running job is either in 'ok' or 'error' state
        if gi.datasets.show_dataset(value[0]['id'])['state'] in ['ok', 'error']:
            break
        log.info('Data manager still running.')
        time.sleep(30)


def data_table_entry_exists(tool_data_client, data_table_name, entry, column='value'):
    '''Checks whether an entry exists in the a specified column in the data_table.'''
    try:
        data_table_content = tool_data_client.show_data_table(data_table_name)
    except:
        raise Exception('Table "%s" does not exist' % (data_table_name))

    try:
        column_index = data_table_content.get('columns').index(column)
    except:
        raise Exception('Column "%s" does not exist in %s' % (column, data_table_name))

    for field in data_table_content.get('fields'):
        if field[column_index] == entry:
            return True
    return False


def get_name_from_inputs(input_dict):
    '''Returns the value that will most likely be recorded in the "name" column of the datatable. Or returns None'''
    possible_keys = ['name', 'sequence_name']  # In order of importance!
    for key in possible_keys:
        if bool(input_dict.get(key)):
            return input_dict.get(key)
    return None


def get_value_from_inputs(input_dict):
    '''Returns the value that will most likely be recorded in the "value" column of the datatable. Or returns None'''
    possible_keys = ['value', 'sequence_id', 'dbkey']  # In order of importance!
    for key in possible_keys:
        if bool(input_dict.get(key)):
            return input_dict.get(key)
    return None


def input_entries_exist_in_data_tables(tool_data_client, data_tables, input_dict):
    '''Checks whether name and value entries from the input are already present in the data tables.
    If an entry is missing in of the tables, this function returns False'''
    value_entry = get_value_from_inputs(input_dict)
    name_entry = get_name_from_inputs(input_dict)

    # Return False if name and value entries are both none
    if not bool(value_entry) and not bool(name_entry):
        return False

    # Check every data table for existance of name and value
    # Return False as soon as entry is not present
    for data_table in data_tables:
        if bool(value_entry):
            if not data_table_entry_exists(tool_data_client, data_table, value_entry, column='value'):
                return False
        if bool(name_entry):
            if not data_table_entry_exists(tool_data_client, data_table, name_entry, column='name'):
                return False
    # If all checks are passed the entries are present in the database tables.
    return True


def run_dm(args):
    url = args.galaxy or DEFAULT_URL
    if args.api_key:
        gi = GalaxyInstance(url=url, key=args.api_key)
    else:
        gi = GalaxyInstance(url=url, email=args.user, password=args.password)
    # should test valid connection
    # The following should throw a ConnectionError when invalid API key or password
    genomes = gi.genomes.get_genomes()  # Does not get genomes but preconfigured dbkeys
    log.info('Number of possible dbkeys: %s' % str(len(genomes)))

    tool_data_client = ToolDataClient(gi)

    conf = yaml.load(open(args.config))
    for dm in conf.get('data_managers'):
        for item in dm.get('items', ['']):
            dm_id = dm['id']
            params = dm['params']
            log.info('Running DM: %s' % dm_id)
            inputs = dict()
            # Iterate over all parameters, replace occurences of {{item}} with the current processing item
            # and create the tool_inputs dict for running the data manager job
            for param in params:
                key, value = param.items()[0]
                value = re.sub(r'{{\s*item\s*}}', item, value, flags=re.IGNORECASE)
                inputs.update({key: value})

            data_tables = dm.get('data_table_reload', [])
            # Only run if not run before.
            if input_entries_exist_in_data_tables(tool_data_client, data_tables, inputs) and not args.overwrite:
                log.info('%s already run for %s' % (dm_id, str(inputs)))
            else:
                # run the DM-job
                job = gi.tools.run_tool(history_id=None, tool_id=dm_id, tool_inputs=inputs)
                wait(gi, job)
                log.info('Reloading data managers table.')
                for data_table in data_tables:
                    # reload two times
                    for i in range(2):
                        tool_data_client.reload_data_table(str(data_table))
                        time.sleep(5)


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
    return parser


def main():
    parser = _parser()
    args = parser.parse_args()
    if args.verbose:
        log.basicConfig(level=log.DEBUG)

    log.info("Running data managers...")
    run_dm(args)


if __name__ == '__main__':
    main()
