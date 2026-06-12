"""Tests for the offline `shed-tools validate` path.

The Tool Shed is faked via monkeypatching so these run without any network or
Galaxy connection.
"""

import textwrap

import pytest

from ephemeris import shed_tools_methods
from ephemeris.shed_tools import main as shed_tools_cli
from ephemeris.shed_tools_methods import validate_against_tool_shed

DEFAULT_TOOL_SHED_URL = "https://toolshed.g2.bx.psu.edu/"

# What our fake Tool Shed reports as installable, keyed by (name, owner).
FAKE_INSTALLABLE = {
    ("bwa", "devteam"): ["051eba708f43", "4d82cf59895e"],
    ("tabular_to_fasta", "devteam"): ["0b4e36026794"],
    ("empty_repo", "devteam"): [],  # exists but nothing installable
}


class _FakeRepositoriesClient:
    def get_ordered_installable_revisions(self, name, owner):
        key = (name, owner)
        if key not in FAKE_INSTALLABLE:
            raise Exception(f"No repository named {name} found with owner {owner}")
        return FAKE_INSTALLABLE[key]


class _FakeToolShedInstance:
    def __init__(self, url):
        self.url = url
        self.repositories = _FakeRepositoriesClient()


@pytest.fixture(autouse=True)
def fake_tool_shed(monkeypatch):
    monkeypatch.setattr(shed_tools_methods, "ToolShedInstance", _FakeToolShedInstance)


def _write(tmp_path, content):
    path = tmp_path / "tools.yaml"
    path.write_text(textwrap.dedent(content))
    return str(path)


def test_validate_against_tool_shed_success():
    repos = [{"name": "bwa", "owner": "devteam", "revisions": ["051eba708f43", "4d82cf59895e"]}]
    assert validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL) == []


def test_validate_against_tool_shed_no_pinned_revision_just_existence():
    repos = [{"name": "bwa", "owner": "devteam"}]
    assert validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL) == []


def test_validate_against_tool_shed_bad_revision():
    repos = [{"name": "bwa", "owner": "devteam", "revisions": ["deadbeefdead"]}]
    errors = validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL)
    assert len(errors) == 1
    assert "deadbeefdead" in errors[0]
    assert "not installable" in errors[0]


def test_validate_against_tool_shed_changeset_revision_key():
    # A single pinned `changeset_revision` (not a `revisions` list) is also checked.
    repos = [{"name": "bwa", "owner": "devteam", "changeset_revision": "deadbeefdead"}]
    errors = validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL)
    assert len(errors) == 1
    assert "deadbeefdead" in errors[0]


def test_validate_against_tool_shed_empty_installable():
    repos = [{"name": "empty_repo", "owner": "devteam", "revisions": ["abc"]}]
    errors = validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL)
    assert len(errors) == 1
    assert "does not exist" in errors[0]


def test_validate_against_tool_shed_query_error():
    repos = [{"name": "missing", "owner": "nobody"}]
    errors = validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL)
    assert len(errors) == 1
    assert "failed to query tool shed" in errors[0]


def test_validate_against_tool_shed_queries_once_per_repo(monkeypatch):
    calls = []
    original = _FakeRepositoriesClient.get_ordered_installable_revisions

    def counting(self, name, owner):
        calls.append((name, owner))
        return original(self, name, owner)

    monkeypatch.setattr(_FakeRepositoriesClient, "get_ordered_installable_revisions", counting)
    repos = [{"name": "bwa", "owner": "devteam", "revisions": ["051eba708f43", "4d82cf59895e"]}]
    validate_against_tool_shed(repos, DEFAULT_TOOL_SHED_URL)
    assert calls == [("bwa", "devteam")]


def test_cli_validate_structural_only_good(tmp_path):
    path = _write(
        tmp_path,
        """
        tools:
        - name: bwa
          owner: devteam
          revisions:
          - 'deadbeefdead'
        """,
    )
    # Bad revision, but --structural-only does not consult the shed.
    assert shed_tools_cli(["validate", path, "--structural-only"]) == 0


def test_cli_validate_structural_only_bad_missing_name(tmp_path):
    path = _write(
        tmp_path,
        """
        tools:
        - owner: devteam
        """,
    )
    assert shed_tools_cli(["validate", path, "--structural-only"]) == 1


def test_cli_validate_full_good(tmp_path):
    path = _write(
        tmp_path,
        """
        tools:
        - name: bwa
          owner: devteam
          revisions:
          - '051eba708f43'
        - name: tabular_to_fasta
          owner: devteam
          revisions:
          - '0b4e36026794'
        """,
    )
    assert shed_tools_cli(["validate", path]) == 0


def test_cli_validate_full_bad_revision(tmp_path):
    path = _write(
        tmp_path,
        """
        tools:
        - name: bwa
          owner: devteam
          revisions:
          - 'deadbeefdead'
        """,
    )
    assert shed_tools_cli(["validate", path]) == 1


def test_cli_validate_via_tools_file_flag(tmp_path):
    path = _write(
        tmp_path,
        """
        tools:
        - name: bwa
          owner: devteam
          revisions:
          - '051eba708f43'
        """,
    )
    assert shed_tools_cli(["validate", "-t", path]) == 0


def test_cli_validate_missing_file(tmp_path):
    assert shed_tools_cli(["validate", str(tmp_path / "nope.yaml")]) == 1


def test_cli_validate_no_input():
    assert shed_tools_cli(["validate"]) == 1


def test_cli_validate_unknown_key_rejected(tmp_path):
    # A typo'd key (revision -> revisions) must fail structurally rather than
    # silently pass with the pin unchecked.
    path = _write(
        tmp_path,
        """
        tools:
        - name: bwa
          owner: devteam
          revision:
          - '051eba708f43'
        """,
    )
    assert shed_tools_cli(["validate", path, "--structural-only"]) == 1


def test_cli_validate_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    assert shed_tools_cli(["validate", str(path), "--structural-only"]) == 1


def test_cli_validate_non_mapping_root(tmp_path):
    path = _write(
        tmp_path,
        """
        - name: bwa
          owner: devteam
        """,
    )
    assert shed_tools_cli(["validate", str(path), "--structural-only"]) == 1
