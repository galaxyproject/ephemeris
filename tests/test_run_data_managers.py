#!/usr/bin/env python
# Stop pylint complaining from things that are necessary
# for pytest to work.
# pylint: disable=no-self-use,unused-import
import sys
import time

import pytest
import yaml
from docker_for_galaxy import GALAXY_ADMIN_KEY, GALAXY_ADMIN_PASSWORD, GALAXY_ADMIN_USER, start_container  # noqa: F401 prevent unused error

from ephemeris import run_data_managers
from ephemeris.run_data_managers import DataManagers
from ephemeris.shed_tools import InstallRepositoryManager
from ephemeris.sleep import galaxy_wait

AUTH_BY = "key"


class TestRunDataManagers(object):
    """This class tests run-data-managers"""

    def test_install_data_managers(self, start_container):  # noqa: F811 Prevent start_container unused warning.
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
        # Galaxy is restarted because otherwise data tables are not watched.
        container.container.exec_run("supervisorctl restart galaxy:")
        time.sleep(10)  # give time for the services to go down
        galaxy_wait(container.url)

    def test_run_data_managers(self, start_container):  # noqa: F811 Prevent start_container unused warning.
        """Tests an installation using the command line"""
        container = start_container
        argv = ["run-data-managers"]
        if AUTH_BY == "user":
            argv.extend([
                "--user", GALAXY_ADMIN_USER,
                "-p", GALAXY_ADMIN_PASSWORD,
            ])
        else:
            argv.extend(["-a", GALAXY_ADMIN_KEY])
        argv.extend([
            "-g", container.url,
            "--config", "tests/run_data_managers.yaml.test"
        ])
        sys.argv = argv
        run_data_managers.main()

    def test_run_data_managers_installation_skipped(self, start_container):  # noqa: F811 Prevent start_container unused warning.
        container = start_container
        with open("tests/run_data_managers.yaml.test") as config_file:
            configuration = yaml.safe_load(config_file)
        dm = DataManagers(container.gi, configuration)
        install_results = dm.run()
        assert (len(install_results.successful_jobs) == 0)
        assert (len(install_results.skipped_jobs) == 9)
        assert (len(install_results.failed_jobs) == 0)

    def test_run_data_managers_installation_fail(self, start_container, caplog):  # noqa: F811 Prevent start_container unused warning.
        container = start_container
        configuration = dict(
            data_managers=[
                dict(
                    id="data_manager_fetch_genome_all_fasta_dbkey",
                    params=[
                        {'dbkey_source|dbkey_source_selector': 'new'},
                        {'dbkey_source|dbkey': 'INVALID'},
                        {'dbkey_source|dbkey_name': 'INVALID_KEY'},
                        {'sequence_name': 'INVALID'},
                        {'sequence_id': 'INVALID'},
                        {'reference_source|reference_source_selector': 'ncbi'},
                        {'reference_source|requested_identifier': 'INVALID0123'}
                    ],
                    data_table_reload=[
                        "all_fasta",
                        "__dbkeys__"
                    ]

                )
            ]
        )
        dm = DataManagers(container.gi, configuration)
        with pytest.raises(RuntimeError):
            dm.run()
        assert ("HTTP Error 404" in caplog.text)
        assert ("Not all jobs successful! aborting..." in caplog.text)
        assert ("finished with exit code: 1. Stderr: " in caplog.text)
