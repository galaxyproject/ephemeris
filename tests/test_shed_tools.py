#!/usr/bin/env python
# Stop pylint complaining from things that are necessary
# for pytest to work.
# pylint: disable=no-self-use,unused-import

import json
import logging
import os
import tempfile

import pytest

from ephemeris.shed_tools import InstallRepositoryManager

# NOTE: For each series of tests that needs the same container, use the same class.
# The start_container fixture has the "class" scope.


class TestMiscellaneous:
    """This class is for miscellaneous tests that can use the same galaxy container"""

    def test_invalid_keys_in_repo_list(self, caplog, start_container):
        container = start_container
        irm = InstallRepositoryManager(container.gi)
        caplog.set_level(logging.WARNING)
        irm.install_repositories(
            [
                dict(
                    name="bwa",
                    owner="devteam",
                    tool_panel_section_name="NGS: Alignment",
                    sesame_ouvre_toi="Invalid key",
                )
            ],
            log=logging.getLogger(),
        )
        assert "'sesame_ouvre_toi' not a valid key. Will be skipped during parsing" in caplog.text

    @pytest.mark.parametrize("parallel_tests", [1, 2])
    def test_tool_tests(self, caplog, start_container, parallel_tests):
        container = start_container
        irm = InstallRepositoryManager(container.gi)
        caplog.set_level(logging.WARNING)
        repos = [
            {
                "name": "collection_element_identifiers",
                "owner": "iuc",
                "tool_panel_section_label": "NGS: Alignment",
            }
        ]
        log = logging.getLogger()
        irm.install_repositories(repositories=repos, log=log)
        fd, test_result_file = tempfile.mkstemp()
        os.close(fd)
        irm.test_tools(
            test_json=test_result_file,
            repositories=repos,
            log=log,
            parallel_tests=parallel_tests,
        )
        with open(test_result_file) as test_result:
            result = json.load(test_result)
        assert "tests" in result
