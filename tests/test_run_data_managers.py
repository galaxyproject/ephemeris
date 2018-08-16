#!/usr/bin/env python

from docker_for_galaxy import start_container
from ephemeris.shed_tools import InstallRepositoryManager
from ephemeris.sleep import galaxy_wait
import yaml
import time



class TestRunDataManagers(object):
    """This class tests run-data-managers"""
    def test_install_data_managers(self, start_container):
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
        container.container.restart()
        # time.sleep(5)
        galaxy_wait(container.gi)

