#!/usr/bin/env python

from ephemeris.shed_tools_methods import flatten_repo_info


def test_flatten_repo_info():
    test_repositories = [
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             revisions=["1", "2"]),
        dict(name="bowtie2",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revisions=["3", "4"])
    ]
    flattened_repos = flatten_repo_info(test_repositories)
    assert (flattened_repos == [
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revision="1"),
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             changeset_revision="2"),
        dict(name="bowtie2",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment")
    ])


def test_flatten_repo_info_invalid_key():
    test_repositories = [
        dict(name="bwa",
             owner="devteam",
             tool_panel_section_label="NGS: Alignment",
             tool_shed_url="toolshed.g2.bx.psu.edu",
             sesame_ouvre_toi="This is an invalid key")
    ]
    flattened_repos = flatten_repo_info(test_repositories)

    assert "sesame_ouvre_toi" not in flattened_repos[0].keys()
    assert "tool_shed_url" in flattened_repos[0].keys()
