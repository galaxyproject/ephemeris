#!/usr/bin/env python
# Stop pylint complaining from things that are necessary
# for pytest to work.
# pylint : disable no-self-use

import logging

from docker_for_galaxy import start_container

from ephemeris.shed_tools import InstallRepositoryManager

# This line is needed because flake things the import for start_container is not used otherwise.
start_container_is_used = start_container


# NOTE: For each series of tests that needs the same container, use the same class.
# The start_container fixture has the "class" scope.

class TestMiscellaneous(object):
    """This class is for miscellaneous tests that can use the same galaxy container"""

    def test_invalid_keys_in_repo_list(self, caplog, start_container):
        container = start_container
        irm = InstallRepositoryManager(container.gi)
        caplog.set_level(logging.WARNING)
        irm.install_repositories([
            dict(name="bwa",
                 owner="devteam",
                 tool_panel_section_name="NGS: Alignment",
                 sesame_ouvre_toi="Invalid key")
        ], log=logging.getLogger())
        assert "'sesame_ouvre_toi' not a valid key. Will be skipped during parsing" in caplog.text
