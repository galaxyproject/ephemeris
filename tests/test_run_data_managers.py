#!/usr/bin/env python

import sys
import time

import yaml
from docker_for_galaxy import start_container

from ephemeris import run_data_managers
from ephemeris.run_data_managers import DataManagers
from ephemeris.shed_tools import InstallRepositoryManager
from ephemeris.sleep import galaxy_wait


# Use import to fool flake
yes_i_am_imported = start_container


class TestRunDataManagers(object):
    """This class tests run-data-managers"""

    def test_install_data_managers(self, start_container):
        """Install the data_managers on galaxy"""
        container = start_container
        data_managers = [
            dict(name="data_manager_fetch_genome_dbkeys_all_fasta",
                 owner="devteam"),
            dict(name="data_manager_sam_fasta_index_builder",
                 owner="devteam"),
            dict(name="data_manager_bwa_mem_index_builder",
                 owner="devteam")
        ]
        irm = InstallRepositoryManager(container.gi)
        irm.install_repositories(data_managers)
        print("Restart container")
        container.container.exec_run("supervisorctl restart galaxy:")
        time.sleep(10)  # give time for the services to go down
        galaxy_wait(container.url)

    def test_run_data_managers(self, start_container):
        """Tests an installation using the command line"""
        container = start_container
        sys.argv = ["run-data-managers",
                    "--user", "admin@galaxy.org",
                    "-p", "admin",
                    "-g", container.url,
                    "--config", "tests/run_data_managers.yaml.test"]
        run_data_managers.main()

    def test_run_data_managers_installation_skipped(self, start_container):
        container = start_container
        with open("tests/run_data_managers.yaml.test") as conig_file:
            configuration = yaml.load(conig_file)
        dm = DataManagers(container.gi, configuration)
        install_results = dm.run()
        assert (len(install_results.successful_jobs) == 0)
        assert (len(install_results.skipped_jobs) == 9)
        assert (len(install_results.failed_jobs) == 0)
