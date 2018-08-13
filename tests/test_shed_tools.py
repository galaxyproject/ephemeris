#!/usr/bin/env python
import logging

from bioblend.galaxy import GalaxyInstance
from docker_for_galaxy import start_container

from ephemeris.shed_tools import InstallRepositoryManager


def test_invalid_keys_in_repo_list(caplog):
    container = start_container()
    gi = GalaxyInstance(container.url, key="admin")
    irm = InstallRepositoryManager(gi)
    caplog.set_level(logging.WARNING)
    irm.install_repositories([
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_name="NGS: Alignment",
             sesame_ouvre_toi="Invalid key")
    ], log=logging.getLogger())
    assert "'sesame_ouvre_toi' not a valid key. Will be skipped during parsing" in caplog.text
