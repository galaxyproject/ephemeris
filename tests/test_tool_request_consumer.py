import io
import json
import os
import pathlib
import re
import sys
from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace
from urllib.parse import (
    parse_qs,
    urlsplit,
)

import pytest
import requests
import yaml
from bioblend import ConnectionError as BioblendError

from ephemeris import tool_request_consumer
from ephemeris.tool_request_consumer import (
    _shed,
    emit,
    emit_item,
    fetch_notifications,
    installed,
    main,
    MAX_BODY_LENGTH,
    merge_tool_list,
    reply,
    ReplyFailed,
    select_requests,
)

NOTIFICATIONS = json.loads((pathlib.Path(__file__).parent / "tool_installation_requests.json").read_text())
SHED = "https://toolshed.g2.bx.psu.edu/"
LABEL = "Tools from user request"


def _request(notification_id, tools=None, **fields):
    notification = next(n for n in NOTIFICATIONS if n["id"] == notification_id)
    if tools is not None:
        notification = dict(notification, content=dict(notification["content"], tools=tools))
    return dict(notification, **fields)


def _emit(notification_id, tools=None, **options):
    return emit_item(_request(notification_id, tools), SHED, LABEL, **options)


def _galaxy_get(url, params=None):
    """Answer like Galaxy's notifications API, which no longer has requests it expired."""
    notification = next((n for n in NOTIFICATIONS if url.endswith(n["id"])), None)
    return SimpleNamespace(
        status_code=200 if notification else 404, json=lambda: notification, raise_for_status=lambda: None
    )


def _outside_code(markdown):
    without_blocks = re.sub(r"^(`{3,})\n.*?\n\1$", "", markdown, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", without_blocks)


def _render_yaml(monkeypatch, items, tools_file):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(items)))
    main(["render-yaml", "--tools-file", str(tools_file), "-o", str(tools_file)])
    return yaml.safe_load(tools_file.read_text())


class FakeToolShed:
    """A Tool Shed with a few repositories, failing every lookup with ``error`` if given."""

    # Repository id: owner, name, and installable revisions as (numeric revision, changeset, tool versions).
    REPOSITORIES = {
        "f1": (
            "iuc",
            "fastp",
            [(None, "aaaaaaaaaaaa", {}), (0, "36be11c58dac", {}), (1, "68386e630362", {"fastp": "1.3.6+galaxy0"})],
        ),
        "s1": ("devteam", "samtools_sort", [(0, "5c2b3a4d1e0f", {"samtools_sort": "1.13"})]),
        "b1": (
            "devteam",
            "bwa",
            [
                (0, "4a196b9c72c2", {"bwa": "0.7.18", "bwa_mem": "0.7.18"}),
                (1, "1dfc975b48d5", {"bwa": "0.7.19", "bwa_mem": "0.7.18"}),
                (2, "2e7d0a1b3c4f", {"bwa": "0.7.19", "bwa_mem": "0.7.19"}),
            ],
        ),
        "j1": ("jjohnson", "regex_find_replace", [(0, "9ea374bb0350", {"regexColumn1": "0.1.0"})]),
        "k1": ("kellrott", "regex_replace", [(0, "9a77d5fca67c", {"regex_replace": "1.0.0"})]),
        # A suite, with no tool named like the repository.
        "t1": (
            "iuc",
            "bedtools",
            [(0, "a1b2c3d4e5f6", {"bedtools_intersectbed": "2.31.1+galaxy0", "bedtools_sortbed": "2.31.1+galaxy0"})],
        ),
    }

    def __init__(self, error=None):
        self.url = SHED + "api"
        self.error = error
        self.requests = []
        self.repositories = SimpleNamespace(get_repositories=self.get_repositories)

    def get_repositories(self, name=None, owner=None):
        self.requests.append((name, owner))
        if self.error:
            raise self.error
        return [
            {"id": key, "owner": o, "name": n}
            for key, (o, n, _) in self.REPOSITORIES.items()
            if n == name and owner in (None, o)
        ]

    def make_get_request(self, url, params=None):
        repository_id = url.removeprefix(f"{self.url}/repositories/").removesuffix("/metadata")
        metadata = {
            f"{numeric}:{changeset}": {
                "numeric_revision": numeric,
                "changeset_revision": changeset,
                "tools": [{"id": tool_id, "version": version} for tool_id, version in tools.items()],
            }
            for numeric, changeset, tools in self.REPOSITORIES[repository_id][2]
        }
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: metadata)


@pytest.fixture(autouse=True)
def fake_tool_shed(monkeypatch):
    def clear_caches():
        tool_request_consumer._repositories.cache_clear()
        tool_request_consumer._installable_revisions.cache_clear()

    def install(**kwargs):
        clear_caches()
        shed = FakeToolShed(**kwargs)
        monkeypatch.setattr(tool_request_consumer, "_shed", lambda url: shed)
        return shed

    install()
    yield install
    clear_caches()


def test_emit_pins_requested_versions_in_a_pr():
    form = _emit("b2486a20bc56b90f")
    assert form["action"] == "pr"
    assert form["tools"] == [
        {
            "name": "fastp",
            "owner": "iuc",
            "tool_shed_url": SHED,
            "tool_panel_section_label": LABEL,
            "revisions": ["68386e630362"],
        }
    ]
    assert "toolrequester@galaxy.test" not in json.dumps(form)

    workflow = _emit("0aab0e4c25198ad8")
    assert workflow["action"] == "pr"
    assert [(t["owner"], t["name"], t["revisions"]) for t in workflow["tools"]] == [
        ("jjohnson", "regex_find_replace", ["9ea374bb0350"]),
        ("kellrott", "regex_replace", ["9a77d5fca67c"]),
    ]

    # Two tools from one repository become one entry, each pinned to the newest revision with its version.
    same_repo = _emit("5ba8d2a3c1e7f046")
    assert [(t["owner"], t["name"], t["revisions"]) for t in same_repo["tools"]] == [
        ("devteam", "bwa", ["4a196b9c72c2", "2e7d0a1b3c4f"]),
    ]

    # A free-text request means the version of the tool named like the repository, not of bwa_mem.
    by_name = _emit("b2486a20bc56b90f", tools=[{"name": "BWA", "requested_version": "0.7.18"}])
    assert by_name["tools"][0]["revisions"] == ["4a196b9c72c2"]
    assert by_name["title"] == "Install bwa 0.7.18"


def test_emit_falls_back_to_an_issue():
    unavailable = _emit("d413a19dec13d11e")
    assert unavailable["action"] == "issue"
    assert "| `bwa 0.7.17` | not resolved: `no installable revision has version 0.7.17` | |" in unavailable["body"]

    unknown = _emit("b887d74393f85b6d")
    assert unknown["action"] == "issue"
    assert unknown["tools"] == []

    # A request without a version stays an issue for the admins to judge.
    unpinned = _emit("b2486a20bc56b90f", tools=[{"name": "fastp", "requested_version": None}])
    assert unpinned["action"] == "issue"
    assert unpinned["tools"] == [
        {"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "tool_panel_section_label": LABEL}
    ]

    workflow_without_version = _emit(
        "0aab0e4c25198ad8",
        tools=[{"name": "regex_replace", "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/kellrott/regex_replace"}],
    )
    assert workflow_without_version["action"] == "issue"

    missing_repository = _emit(
        "0aab0e4c25198ad8",
        tools=[{"name": "nothing", "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/no-such-owner/no_such_repo"}],
    )
    assert missing_repository["action"] == "issue"
    assert missing_repository["tools"] == []

    # Another Tool Shed than the configured one is not trusted.
    other_tool_shed = _emit(
        "0aab0e4c25198ad8",
        tools=[
            {
                "name": "fastp",
                "tool_shed_id": "testtoolshed.g2.bx.psu.edu/repos/iuc/fastp",
                "requested_version": "1.3.6+galaxy0",
            }
        ],
    )
    assert other_tool_shed["action"] == "issue"
    assert other_tool_shed["tools"] == []


def test_emit_keeps_user_text_out_of_markdown(fake_tool_shed):
    fake_tool_shed()
    item = _emit(
        "b2486a20bc56b90f",
        tools=[
            {"name": "@octocat | <b>x</b>"},
            {"name": "x", "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/@octocat/<b>x|y</b>"},
        ],
    )
    assert "@octocat" not in _outside_code(item["body"])
    assert "<b>" not in _outside_code(item["body"])

    # GitLab closes issues that a merge request description references, even in code.
    referencing = _emit(
        "b2486a20bc56b90f",
        tools=[{"name": "fastp", "requested_version": "1.3.6+galaxy0", "description": "fixes #3"}],
    )
    referencing_request = _request("b2486a20bc56b90f")
    referencing_request["content"] = dict(referencing_request["content"], additional_remarks="closes #4")
    for body in (referencing["body"], emit_item(referencing_request, SHED, LABEL)["body"]):
        assert not re.search(r"#\d", body)

    # Galaxy replaces the workflow id with its own, but older or other servers may pass on what users sent.
    workflow_request = _request("0aab0e4c25198ad8")
    assert "Needed by workflow `33b43b4e7093c91f`." in emit_item(workflow_request, SHED, LABEL)["body"]
    workflow_request["content"] = dict(workflow_request["content"], workflow_id="x` @octocat fixes #1 <b>x</b> `")
    workflow_body = emit_item(workflow_request, SHED, LABEL)["body"]
    assert "@octocat" not in _outside_code(workflow_body)
    assert "<b>" not in _outside_code(workflow_body)
    assert not re.search(r"#\d", workflow_body)

    # GitLab rejects titles over 255 characters, and GitHub bodies over 65536.
    long_names = _emit("b2486a20bc56b90f", tools=[{"name": "x" * 255}, {"name": "y" * 255}])
    assert len(long_names["title"]) <= 255


def test_emit_fits_long_requests_into_the_body_limit(fake_tool_shed):
    fake_tool_shed()
    # The largest request Galaxy accepts: 50 tools with long URLs and descriptions.
    unnamed = {"tool_url": "https://x.org/ @victim " + "u" * 2000, "description": "d @victim " * 500}
    pinned = {"name": "fastp", "requested_version": "1.3.6+galaxy0", "description": "d" * 5000}
    item = _emit("b2486a20bc56b90f", tools=[unnamed] * 30 + [pinned] * 20)

    assert len(item["body"]) <= MAX_BODY_LENGTH
    assert "(Truncated, the full request is in Galaxy.)" in item["body"]
    assert "@victim" not in _outside_code(item["body"])
    # The tool list entries come last, whole.
    entries = item["body"].rsplit("Tool list entries:\n```\n", 1)[1]
    assert entries.endswith("\n```")
    assert yaml.safe_load(entries[: -len("\n```")])["tools"][0]["revisions"] == ["68386e630362"]


def test_emit_looks_tool_names_up_exactly(fake_tool_shed):
    shed = fake_tool_shed()
    item = _emit(
        "b2486a20bc56b90f",
        tools=[
            {"name": " FastP ", "requested_version": "1.3.6+galaxy0"},
            {"name": "fastp", "requested_version": "1.3.6+galaxy0"},
            # Repository names only hold lower case letters, digits and underscores.
            {"name": "bowtie2: map"},
        ],
    )
    assert item["tools"] == [
        {
            "name": "fastp",
            "owner": "iuc",
            "tool_shed_url": SHED,
            "tool_panel_section_label": LABEL,
            "revisions": ["68386e630362"],
        }
    ]
    assert shed.requests == [("fastp", None), ("bowtie2_map", None)]


def test_emit_links_tools_no_repository_is_named_like(fake_tool_shed):
    shed = fake_tool_shed()
    template = "https://github.com/org/tools-dev/issues/new?title={title}&body={body}&labels=tool%20request"
    tools = [
        # The Tool Shed spells this samtools_sort.
        {"name": "Samtools sort"},
        {"name": "NewTool @victim", "tool_url": "https://example.org/newtool", "description": "Does (new) things."},
    ]
    item = emit_item(_request("b2486a20bc56b90f", tools), SHED, LABEL, wrapper_request_url=template)

    assert ("samtools_sort", None) in shed.requests
    [(name, link)] = re.findall(r"\[Request a wrapper for `([^`]*)`\]\((\S+)\)", item["body"])
    assert name == "NewTool @victim"
    query = parse_qs(urlsplit(link).query)
    assert query["title"] == ["Tool request: NewTool @victim"]
    assert "Does (new) things." in query["body"][0]
    assert "Homepage: https://example.org/newtool" in query["body"][0]
    assert query["labels"] == ["tool request"]
    # The link names the tool as code and encodes what users typed.
    assert "@victim" not in _outside_code(item["body"])

    # Tools the Tool Shed has get no link.
    listed = emit_item(_request("b2486a20bc56b90f", [{"name": "fastp"}]), SHED, LABEL, wrapper_request_url=template)
    assert "Request a wrapper" not in listed["body"]


def test_emit_pins_tools_without_a_version_to_the_newest_revision(fake_tool_shed):
    fake_tool_shed()
    by_name = emit_item(_request("b2486a20bc56b90f", [{"name": "fastp"}]), SHED, LABEL, pin_latest=True)
    assert by_name["action"] == "pr"
    assert by_name["tools"][0]["revisions"] == ["68386e630362"]
    # The tools of a repository can have different versions, so only a named tool's version goes in the title.
    assert by_name["title"] == "Install fastp"

    workflow_tool = {"name": "fastp", "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/iuc/fastp"}
    by_id = emit_item(_request("0aab0e4c25198ad8", [workflow_tool]), SHED, LABEL, pin_latest=True)
    assert by_id["title"] == "Install fastp 1.3.6+galaxy0"


def test_emit_leaves_versions_of_suites_to_the_admins(fake_tool_shed):
    fake_tool_shed()
    # Any tool of the suite could have the requested version.
    suite = _emit("b2486a20bc56b90f", tools=[{"name": "bedtools", "requested_version": "2.31.1+galaxy0"}])
    assert suite["action"] == "issue"
    assert "bedtools has several tools" in suite["body"]
    nameless_tool = {
        "name": None,
        "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/iuc/bedtools",
        "requested_version": "2.31.1+galaxy0",
    }
    assert _emit("0aab0e4c25198ad8", tools=[nameless_tool])["action"] == "issue"

    # A workflow names the tool.
    workflow_tool = {
        "name": "bedtools_sortbed",
        "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/iuc/bedtools",
        "requested_version": "2.31.1+galaxy0",
    }
    assert _emit("0aab0e4c25198ad8", tools=[workflow_tool])["action"] == "pr"
    # A repository with one tool, named otherwise, leaves no doubt.
    single = _emit("b2486a20bc56b90f", tools=[{"name": "regex_find_replace", "requested_version": "0.1.0"}])
    assert single["action"] == "pr"
    assert single["tools"][0]["revisions"] == ["9ea374bb0350"]
    # Without a version, the newest revision has every tool of the suite.
    latest = emit_item(_request("b2486a20bc56b90f", [{"name": "bedtools"}]), SHED, LABEL, pin_latest=True)
    assert latest["action"] == "pr"


def test_emit_gives_unpinned_tools_their_own_entry(fake_tool_shed):
    fake_tool_shed()
    item = _emit(
        "b2486a20bc56b90f",
        tools=[{"name": "fastp", "requested_version": "1.3.6+galaxy0"}, {"name": "fastp"}],
    )
    assert item["action"] == "issue"
    entry = {"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "tool_panel_section_label": LABEL}
    assert item["tools"] == [dict(entry, revisions=["68386e630362"]), entry]


def test_emit_waits_a_day_for_the_tool_shed(fake_tool_shed):
    now = datetime.now(timezone.utc).isoformat()
    fresh = _request("b2486a20bc56b90f", id="fresh", publication_time=now)
    also_fresh = _request("b2486a20bc56b90f", id="also_fresh", publication_time=now)
    old = _request("b2486a20bc56b90f", id="old", publication_time="2026-01-01T00:00:00")

    # Any error, even one the Tool Shed may give again, leaves fresh requests for the next run.
    for status in (403, 502):
        shed = fake_tool_shed(error=BioblendError(f"GET: error {status}", status_code=status))
        [item] = emit([fresh, old], SHED, LABEL)
        assert item["notification_id"] == "old"
        assert item["action"] == "issue"
        assert f"not looked up, the Tool Shed failed: GET: error {status}" in item["body"]
        assert len(shed.requests) == 2

    # A Tool Shed that does not answer at all is not asked again in the same run, and the requests after
    # the one that failed wait, however old they are.
    shed = fake_tool_shed(error=BioblendError("Connection refused"))
    assert [i["notification_id"] for i in emit([old, fresh, also_fresh], SHED, LABEL)] == ["old"]
    assert emit([fresh, old], SHED, LABEL) == []
    assert len(shed.requests) == 2
    assert _shed("https://toolshed.invalid/").timeout == tool_request_consumer.TOOL_SHED_TIMEOUT


def test_emit_titles_pull_requests_with_tool_shed_data_only(fake_tool_shed):
    fake_tool_shed()
    # Only text after the last "://" used to be compared with the configured Tool Shed.
    disguised = _emit(
        "0aab0e4c25198ad8",
        tools=[
            {
                "name": None,
                "tool_shed_id": "Fixes #1 @victim x://toolshed.g2.bx.psu.edu/repos/iuc/fastp",
                "requested_version": "1.3.6+galaxy0",
            }
        ],
    )
    assert disguised["action"] == "issue"
    assert disguised["tools"] == []

    by_id = _emit(
        "0aab0e4c25198ad8",
        tools=[
            {
                "name": None,
                "tool_shed_id": "http://ToolShed.G2.bx.psu.edu/repos/iuc/fastp",
                "requested_version": "1.3.6+galaxy0",
            }
        ],
    )
    assert by_id["action"] == "pr"
    assert by_id["title"] == "Install fastp 1.3.6+galaxy0"

    by_name = _emit("b2486a20bc56b90f", tools=[{"name": "FASTP", "requested_version": "1.3.6+galaxy0"}])
    assert by_name["action"] == "pr"
    assert by_name["title"] == "Install fastp 1.3.6+galaxy0"

    # Issue titles keep what users typed, on one line.
    multiline = _emit("b2486a20bc56b90f", tools=[{"name": "fast\np\n\nFixes #1"}])
    assert multiline["action"] == "issue"
    assert multiline["title"] == "Install fast p Fixes #1"


def test_select_requests_skips_seen_requests_and_other_categories():
    seen = dict(NOTIFICATIONS[0], id="a1", seen_time="2026-10-09T13:00:00")
    message = dict(NOTIFICATIONS[0], id="a3", category="message", content={"category": "message"})
    unseen_ids = [n["id"] for n in NOTIFICATIONS]

    assert [n["id"] for n in select_requests(NOTIFICATIONS + [seen, message])] == unseen_ids


def test_select_requests_picks_up_requests_an_admin_read():
    read = dict(NOTIFICATIONS[0], id="r1", seen_time="2026-10-09T13:00:00", publication_time="2026-10-09T12:00:00")
    handled = dict(read, id="r2")
    # Sent before the first issue or pull request, so presumably handled by hand.
    older = dict(read, id="r3", publication_time="2026-09-01T00:00:00")
    # Handled, but its requester may not have been told yet.
    unseen = dict(NOTIFICATIONS[0], id="r4")
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)

    # Seen moments ago, maybe by the run that handled it, whose issue the forge does not list yet.
    just_read = dict(read, id="r5", seen_time=datetime.now(timezone.utc).isoformat())

    picked = select_requests([read, handled, older, unseen, just_read], handled={"r2", "r4"}, seen_since=since)
    assert [n["id"] for n in picked] == ["r1", "r4"]


def test_fetch_notifications_reads_all_at_once():
    # Galaxy does not order notifications, so pages could skip some.
    notifications = [{"id": str(i)} for i in range(250)]

    def get(url, params):
        assert params == {"limit": 0}
        return SimpleNamespace(json=lambda: notifications, raise_for_status=lambda: None)

    gi = SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)
    assert fetch_notifications(gi) == notifications


def test_render_yaml_adds_revisions_to_existing_entries(tmp_path, monkeypatch):
    existing = {
        "install_tool_dependencies": True,
        "tools": [
            {
                "name": "fastp",
                "owner": "iuc",
                "tool_panel_section_label": "Quality Control",
                "revisions": ["36be11c58dac"],
            },
            # Without revisions the entry follows the latest revision.
            {"name": "regex_find_replace", "owner": "jjohnson"},
        ],
    }
    new_entry = {
        "name": "regex_replace",
        "owner": "kellrott",
        "tool_shed_url": SHED,
        "tool_panel_section_label": LABEL,
        "revisions": ["9a77d5fca67c"],
    }
    items = [
        {
            "action": "pr",
            "tools": [{"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "revisions": ["68386e630362"]}],
        },
        {"action": "pr", "tools": [new_entry]},
        {
            "action": "pr",
            "tools": [{"name": "regex_find_replace", "owner": "jjohnson", "revisions": ["9ea374bb0350"]}],
        },
        # Issue items wait for the admins.
        {"action": "issue", "tools": [{"name": "bwa", "owner": "devteam", "revisions": ["4a196b9c72c2"]}]},
    ]

    tools_file = tmp_path / "tools.yaml"
    tools_file.write_text(yaml.safe_dump(existing))

    merged = _render_yaml(monkeypatch, items, tools_file)

    assert merged == {
        "install_tool_dependencies": True,
        "tools": [
            {
                "name": "fastp",
                "owner": "iuc",
                "tool_panel_section_label": "Quality Control",
                "revisions": ["36be11c58dac", "68386e630362"],
            },
            {"name": "regex_find_replace", "owner": "jjohnson"},
            new_entry,
        ],
    }
    assert _render_yaml(monkeypatch, items, tools_file) == merged


def test_render_yaml_starts_a_tool_list_that_installs_dependencies(tmp_path, monkeypatch):
    items = [{"action": "pr", "tools": [{"name": "fastp", "owner": "iuc"}]}]

    # shed-tools only installs dependencies when the tool list asks for them.
    assert _render_yaml(monkeypatch, items, tmp_path / "new.yaml") == {
        "install_repository_dependencies": True,
        "install_resolver_dependencies": True,
        "tools": [{"name": "fastp", "owner": "iuc"}],
    }


def test_render_yaml_reads_revisions_like_shed_tools():
    existing = {
        "tools": [
            # shed-tools installs the latest revision for these.
            {"name": "null_revisions", "owner": "o", "revisions": None},
            {"name": "no_revisions", "owner": "o", "revisions": []},
            {"name": "changeset_pin", "owner": "o", "changeset_revision": "36be11c58dac"},
            # An unquoted revision made of digits loads as a number.
            {"name": "numeric", "owner": "o", "revisions": [123456789012]},
        ]
    }
    items = [
        {
            "action": "pr",
            "tools": [
                {"name": "null_revisions", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "no_revisions", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "changeset_pin", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "numeric", "owner": "o", "revisions": ["123456789012"]},
            ],
        }
    ]

    assert merge_tool_list(existing, items)["tools"] == [
        {"name": "null_revisions", "owner": "o", "revisions": None},
        {"name": "no_revisions", "owner": "o", "revisions": []},
        {"name": "changeset_pin", "owner": "o", "revisions": ["36be11c58dac", "68386e630362"]},
        {"name": "numeric", "owner": "o", "revisions": [123456789012]},
    ]


def test_render_yaml_leaves_a_tool_list_that_has_the_revisions_alone(tmp_path, monkeypatch):
    # Listed twice, and once with an http:// Tool Shed URL.
    tools = """\
# Requested tools
tools:
  - name: fastp
    owner: iuc
    tool_shed_url: http://toolshed.g2.bx.psu.edu
    revisions: ['68386e630362']
  - name: fastp
    owner: iuc
    revisions: ['36be11c58dac']
"""
    tools_file = tmp_path / "tools.yaml"
    tools_file.write_text(tools)
    items = [
        {
            "action": "pr",
            "tools": [{"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "revisions": ["68386e630362"]}],
        }
    ]

    _render_yaml(monkeypatch, items, tools_file)
    assert tools_file.read_text() == tools


def test_reply_notifies_the_exact_requester():
    # Galaxy's f_email filter is a substring match.
    users = [
        {"id": "u1", "email": "old.toolrequester@galaxy.test"},
        {"id": "u2", "email": "toolrequester@galaxy.test"},
    ]
    posted = []
    sent = SimpleNamespace(count=1)

    def post(url, payload):
        posted.append((url, payload))
        return {"total_notifications_sent": sent.count, "notification": {}}

    gi = SimpleNamespace(
        url="http://galaxy.test/api",
        users=SimpleNamespace(get_users=lambda f_email: [u for u in users if f_email in u["email"]]),
        make_get_request=_galaxy_get,
        make_post_request=post,
    )

    assert reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/pull/7")

    [(url, payload)] = posted
    assert url == "http://galaxy.test/api/notifications"
    assert payload["recipients"]["user_ids"] == ["u2"]
    assert payload["notification"]["content"]["category"] == "message"
    # Galaxy stores up to 32 characters, and fails to send a notification with a longer source.
    assert len(payload["notification"]["source"]) <= 32
    assert "https://github.com/org/tools/pull/7" in payload["notification"]["content"]["message"]

    # A requester whose account is gone cannot be answered, which must not stop the run.
    assert not reply(gi, "b887d74393f85b6d", "https://github.com/org/tools/issues/8")
    assert len(posted) == 1

    # Galaxy sends nothing to users who turned message notifications off.
    sent.count = 0
    assert not reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/pull/7")


def test_reply_reports_galaxy_refusing_it(monkeypatch, caplog):
    def post(url, payload):
        raise BioblendError("Unexpected HTTP status code: 429", status_code=429)

    gi = SimpleNamespace(
        url="http://galaxy.test/api",
        users=SimpleNamespace(get_users=lambda f_email: [{"id": "u2", "email": f_email}]),
        make_get_request=_galaxy_get,
        make_post_request=post,
    )
    monkeypatch.setattr(tool_request_consumer, "get_galaxy_connection", lambda args, log, login_required: gi)

    # Galaxy limits how many notifications an account sends per minute, so the next run tries again.
    assert main(["reply", "--notification-id", "b2486a20bc56b90f", "--url", "https://github.com/org/tools/pull/7"]) == 1
    assert "Could not tell the requester of b2486a20bc56b90f" in caplog.text


def test_reply_tells_how_the_request_ended():
    posted = []

    def post(url, payload):
        posted.append(payload["notification"]["content"])
        return {"total_notifications_sent": 1, "notification": {}}

    gi = SimpleNamespace(
        url="http://galaxy.test/api",
        users=SimpleNamespace(get_users=lambda f_email: [{"id": "u2", "email": f_email}]),
        make_get_request=_galaxy_get,
        make_post_request=post,
    )

    # Admins without a tool list repository have no link to give.
    assert reply(gi, "b2486a20bc56b90f", state="installed")
    assert posted[-1]["subject"] == "Your requested tools are installed"
    assert "http" not in posted[-1]["message"]
    assert reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/issues/8", state="closed")
    assert posted[-1]["message"].endswith(": https://github.com/org/tools/issues/8")
    # Galaxy deletes requests some months after they were sent.
    assert not reply(gi, "0000000000000000", state="closed")
    assert len(posted) == 2


def test_installed_asks_galaxy_for_the_requested_tool_versions():
    def galaxy(*guids):
        """A Galaxy that loaded the Tool Shed tools with these ids, and a built-in tool."""
        tools = [{"id": "upload1", "version": "1.1.7"}]
        for guid in guids:
            shed, _, owner, name, _, version = guid.split("/")
            tools.append(
                {
                    "id": guid,
                    "version": version,
                    "tool_shed_repository": {"tool_shed": shed, "owner": owner, "name": name},
                }
            )

        def get(url, params=None):
            assert (url, params) == ("http://galaxy.test/api/tools", {"in_panel": False})
            return SimpleNamespace(json=lambda: tools, raise_for_status=lambda: None)

        return SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)

    fastp = "toolshed.g2.bx.psu.edu/repos/iuc/fastp/fastp/1.3.6+galaxy0"
    newer_fastp = fastp.replace("galaxy0", "galaxy1")
    assert installed(galaxy(fastp), _request("b2486a20bc56b90f"))
    assert not installed(galaxy(newer_fastp), _request("b2486a20bc56b90f"))
    # Without a version, any version counts.
    assert installed(galaxy(newer_fastp), _request("b2486a20bc56b90f", [{"name": "FastP"}]))

    # A workflow's request names the repository and the tool.
    regex = [
        "toolshed.g2.bx.psu.edu/repos/jjohnson/regex_find_replace/regexColumn1/0.1.0",
        "toolshed.g2.bx.psu.edu/repos/kellrott/regex_replace/regex_replace/1.0.0",
    ]
    assert installed(galaxy(*regex), _request("0aab0e4c25198ad8"))
    assert not installed(galaxy(regex[0]), _request("0aab0e4c25198ad8"))
    assert not installed(galaxy(*(r.replace("toolshed", "testtoolshed") for r in regex)), _request("0aab0e4c25198ad8"))

    # A free-text request means the tool named like the repository.
    bwa = _request("b2486a20bc56b90f", [{"name": "bwa", "requested_version": "0.7.18"}])
    bwa_mem = "toolshed.g2.bx.psu.edu/repos/devteam/bwa/bwa_mem/0.7.18"
    assert not installed(galaxy(bwa_mem, "toolshed.g2.bx.psu.edu/repos/devteam/bwa/bwa/0.7.19"), bwa)
    assert installed(galaxy(bwa_mem, "toolshed.g2.bx.psu.edu/repos/devteam/bwa/bwa/0.7.18"), bwa)
    # Nothing is installed for tools that nobody wrapped.
    assert not installed(galaxy(fastp), _request("b2486a20bc56b90f", [{"name": "Foldseek"}]))


def test_reply_waits_for_galaxy_to_send_it_in_a_task(monkeypatch):
    monkeypatch.setattr(tool_request_consumer.time, "sleep", lambda seconds: None)
    # With Celery, Galaxy answers with a task, and sends the notification in it.
    states = {"t1": ["PENDING", "SUCCESS"], "t2": ["STARTED", "FAILURE"], "t3": ["PENDING"] * 3}
    task = SimpleNamespace(id=None)

    def get(url, params=None):
        if "/tasks/" in url:
            state = states[url.split("/")[-2]].pop(0)
            return SimpleNamespace(json=lambda: state, raise_for_status=lambda: None)
        return _galaxy_get(url)

    gi = SimpleNamespace(
        url="http://galaxy.test/api",
        users=SimpleNamespace(get_users=lambda f_email: [{"id": "u2", "email": f_email}]),
        make_get_request=get,
        make_post_request=lambda url, payload: {"id": task.id, "ignored": False, "name": None, "queue": None},
    )

    task.id = "t1"
    assert reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/pull/7")
    # The request then stays unseen, so that the next run answers it.
    task.id = "t2"
    with pytest.raises(ReplyFailed):
        reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/pull/7")
    # A slow Galaxy may still send it, so asking again could repeat the message.
    monkeypatch.setattr(tool_request_consumer, "REPLY_TIMEOUT", -1)
    task.id = "t3"
    assert reply(gi, "b2486a20bc56b90f", "https://github.com/org/tools/pull/7")


def test_run_starts_the_script_that_comes_with_ephemeris(monkeypatch):
    started = []
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(tool_request_consumer.os, "execvp", lambda file, args: started.append((file, args)))

    main(["run"])

    [(file, [_, script])] = started
    assert file == "bash"
    assert pathlib.Path(script).read_text().startswith("#!/usr/bin/env bash")
    # The script runs this command, so it finds the one from the same installation first.
    assert os.environ["PATH"].split(os.pathsep)[0] == os.path.dirname(sys.executable)


def test_emit_reports_galaxy_refusing_it(monkeypatch, caplog):
    def get(url, params=None):
        raise requests.HTTPError("401 Client Error: Unauthorized")

    gi = SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)
    monkeypatch.setattr(tool_request_consumer, "get_galaxy_connection", lambda args, log, login_required: gi)

    assert main(["emit"]) == 1
    assert "Could not read the requests from Galaxy: 401 Client Error" in caplog.text
