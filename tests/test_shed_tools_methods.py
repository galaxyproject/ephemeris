#!/usr/bin/env python

import pytest

from ephemeris.shed_tools_args import parser
from ephemeris.shed_tools_methods import (
    complete_repo_information,
    flatten_repo_info,
)


def test_flatten_repo_info():
    test_repositories = [
        dict(
            name="bwa",
            owner="devteam",
            tool_panel_section_label="NGS: Alignment",
            revisions=["1", "2"],
        ),
        dict(name="bowtie2", owner="devteam", tool_panel_section_label="NGS: Alignment"),
    ]
    flattened_repos = flatten_repo_info(test_repositories)
    assert flattened_repos == [
        dict(
            name="bwa",
            owner="devteam",
            tool_panel_section_label="NGS: Alignment",
            changeset_revision="1",
        ),
        dict(
            name="bwa",
            owner="devteam",
            tool_panel_section_label="NGS: Alignment",
            changeset_revision="2",
        ),
        dict(name="bowtie2", owner="devteam", tool_panel_section_label="NGS: Alignment"),
    ]


@pytest.mark.parametrize("command", ["install", "update"])
def test_dependencies_are_installed_unless_skipped(command):
    args = parser().parse_args([command, "-a", "key"])
    assert (args.install_repository_dependencies, args.install_resolver_dependencies) == (True, True)
    assert args.install_tool_dependencies is False
    skipped = parser().parse_args(
        [command, "-a", "key", "--skip-install-repository-dependencies", "--skip-install-resolver-dependencies"]
    )
    assert (skipped.install_repository_dependencies, skipped.install_resolver_dependencies) == (False, False)


def test_a_tool_can_turn_dependencies_off():
    tool = dict(name="bwa", owner="devteam", changeset_revision="1", install_resolver_dependencies=False)
    repo = complete_repo_information(
        tool,
        default_toolshed_url="https://toolshed.g2.bx.psu.edu/",
        default_install_tool_dependencies=False,
        default_install_repository_dependencies=True,
        default_install_resolver_dependencies=True,
        force_latest_revision=False,
    )
    assert repo["install_resolver_dependencies"] is False
    assert repo["install_repository_dependencies"] is True
