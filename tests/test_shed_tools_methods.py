#!/usr/bin/env python

from ephemeris.shed_tools_methods import *


def test_flatten_repo_info():
    test_repositories = [
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             revisions = ["1","2"]),
        dict(name="bowtie2",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revisions= ["3", "4"])
    ]
    flattened_repos = flatten_repo_info(test_repositories)
    assert(flattened_repos == [
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revision = "1"),
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revision = "2"),
        dict(name="bowtie2",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment")
    ])
