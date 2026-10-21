import io
import json
import pathlib
from types import SimpleNamespace

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


FASTP_ID = "toolshed.g2.bx.psu.edu/repos/iuc/fastp/fastp/1.3.6+galaxy0"


def test_emit_pins_requested_versions_in_a_pr():
    form = _emit("b2486a20bc56b90f")
    assert form == {
        "notification_id": "b2486a20bc56b90f",
        "action": "pr",
        "tools": [
            {
                "name": "fastp",
                "owner": "iuc",
                "tool_shed_url": SHED,
                "tool_panel_section_label": LABEL,
                "revisions": ["68386e630362"],
            }
        ],
        # The ids Galaxy gives the requested tools, so that installed can check them.
        "tool_ids": [FASTP_ID],
        "unresolved": [],
    }
    assert "toolrequester@galaxy.test" not in json.dumps(form)

    workflow = _emit("0aab0e4c25198ad8")
    assert workflow["action"] == "pr"
    assert [(t["owner"], t["name"], t["revisions"]) for t in workflow["tools"]] == [
        ("jjohnson", "regex_find_replace", ["9ea374bb0350"]),
        ("kellrott", "regex_replace", ["9a77d5fca67c"]),
    ]
    assert workflow["tool_ids"] == [
        "toolshed.g2.bx.psu.edu/repos/jjohnson/regex_find_replace/regexColumn1/0.1.0",
        "toolshed.g2.bx.psu.edu/repos/kellrott/regex_replace/regex_replace/1.0.0",
    ]

    # Two tools from one repository become one entry, each pinned to the newest revision with its version.
    same_repo = _emit("5ba8d2a3c1e7f046")
    assert [(t["owner"], t["name"], t["revisions"]) for t in same_repo["tools"]] == [
        ("devteam", "bwa", ["4a196b9c72c2", "2e7d0a1b3c4f"]),
    ]

    # A free-text request means the version of the tool named like the repository, not of bwa_mem.
    by_name = _emit("b2486a20bc56b90f", tools=[{"name": "BWA", "requested_version": "0.7.18"}])
    assert by_name["tools"][0]["revisions"] == ["4a196b9c72c2"]
    assert by_name["tool_ids"] == ["toolshed.g2.bx.psu.edu/repos/devteam/bwa/bwa/0.7.18"]


def test_emit_falls_back_to_an_issue():
    unavailable = _emit("d413a19dec13d11e")
    assert unavailable["action"] == "issue"
    assert unavailable["unresolved"] == ["bwa 0.7.17: no installable revision has version 0.7.17"]

    unknown = _emit("b887d74393f85b6d")
    assert unknown["action"] == "issue"
    assert unknown["tools"] == []

    # A request without a version stays an issue for the admins to judge.
    unpinned = _emit("b2486a20bc56b90f", tools=[{"name": "fastp", "requested_version": None}])
    assert unpinned["action"] == "issue"
    assert unpinned["tools"] == [
        {"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "tool_panel_section_label": LABEL}
    ]
    assert unpinned["tool_ids"] == []

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

    # Another Tool Shed than the configured one is not trusted, also if it is disguised.
    for tool_shed_id in (
        "testtoolshed.g2.bx.psu.edu/repos/iuc/fastp",
        "Fixes #1 @victim x://toolshed.g2.bx.psu.edu/repos/iuc/fastp",
    ):
        other = _emit(
            "0aab0e4c25198ad8",
            tools=[{"name": "fastp", "tool_shed_id": tool_shed_id, "requested_version": "1.3.6+galaxy0"}],
        )
        assert other["action"] == "issue"
        assert other["tools"] == []
    by_id = _emit(
        "0aab0e4c25198ad8",
        tools=[
            {
                "name": "fastp",
                "tool_shed_id": "http://ToolShed.G2.bx.psu.edu/repos/iuc/fastp",
                "requested_version": "1.3.6+galaxy0",
            }
        ],
    )
    assert by_id["action"] == "pr"


def test_emit_leaves_local_workflow_tools_to_the_admins(fake_tool_shed):
    shed = fake_tool_shed()
    # Galaxy sends a workflow's tools that are not from a Tool Shed by their local id only.
    item = _emit("0aab0e4c25198ad8", tools=[{"name": "fastp"}])
    assert item["action"] == "issue"
    assert item["unresolved"] == ["fastp: a tool of the workflow that is not from a Tool Shed"]
    assert shed.requests == []


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
    assert item["unresolved"] == [f"bowtie2: map: no repository named bowtie2: map on {SHED}"]
    assert shed.requests == [("fastp", None), ("bowtie2_map", None)]


def test_emit_pins_tools_without_a_version_to_the_newest_revision():
    by_name = emit_item(_request("b2486a20bc56b90f", [{"name": "fastp"}]), SHED, LABEL, pin_latest=True)
    assert by_name["action"] == "pr"
    assert by_name["tools"][0]["revisions"] == ["68386e630362"]
    assert by_name["tool_ids"] == [FASTP_ID]

    workflow_tool = {"name": "fastp", "tool_shed_id": "toolshed.g2.bx.psu.edu/repos/iuc/fastp"}
    by_id = emit_item(_request("0aab0e4c25198ad8", [workflow_tool]), SHED, LABEL, pin_latest=True)
    assert by_id["tool_ids"] == [FASTP_ID]


def test_emit_leaves_versions_of_suites_to_the_admins():
    # Any tool of the suite could have the requested version.
    suite = _emit("b2486a20bc56b90f", tools=[{"name": "bedtools", "requested_version": "2.31.1+galaxy0"}])
    assert suite["action"] == "issue"
    assert "bedtools has several tools" in suite["unresolved"][0]
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
    assert len(latest["tool_ids"]) > 1


def test_emit_gives_unpinned_tools_their_own_entry():
    item = _emit(
        "b2486a20bc56b90f",
        tools=[{"name": "fastp", "requested_version": "1.3.6+galaxy0"}, {"name": "fastp"}],
    )
    assert item["action"] == "issue"
    entry = {"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "tool_panel_section_label": LABEL}
    assert item["tools"] == [dict(entry, revisions=["68386e630362"]), entry]


def test_emit_leaves_requests_the_tool_shed_fails_on_for_the_next_run(fake_tool_shed):
    first = _request("b2486a20bc56b90f", id="first")
    second = _request("b2486a20bc56b90f", id="second")

    # An error or a slow answer only skips the request it was for.
    for error in (BioblendError("GET: error 502", status_code=502), requests.ReadTimeout("read timed out")):
        shed = fake_tool_shed(error=error)
        assert emit([first, second], SHED, LABEL) == []
        assert len(shed.requests) == 2

    # A Tool Shed that cannot be reached is not asked again in the same run.
    shed = fake_tool_shed(error=requests.ConnectionError("Connection refused"))
    assert emit([first, second], SHED, LABEL) == []
    assert len(shed.requests) == 1
    assert _shed("https://toolshed.invalid/").timeout == tool_request_consumer.TIMEOUT


def test_select_requests_skips_seen_requests_and_other_categories():
    seen = dict(NOTIFICATIONS[0], id="a1", seen_time="2026-10-09T13:00:00")
    message = dict(NOTIFICATIONS[0], id="a3", category="message", content={"category": "message"})
    unseen_ids = [n["id"] for n in NOTIFICATIONS]

    assert [n["id"] for n in select_requests(NOTIFICATIONS + [seen, message])] == unseen_ids


def test_fetch_notifications_reads_all_at_once():
    # Galaxy does not order notifications, so pages could skip some.
    notifications = [{"id": str(i)} for i in range(250)]

    def get(url, params):
        assert params == {"limit": 0}
        return SimpleNamespace(json=lambda: notifications, raise_for_status=lambda: None)

    gi = SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)
    assert fetch_notifications(gi) == notifications


def test_render_yaml_adds_revisions_to_existing_entries(tmp_path, monkeypatch, capsys):
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
            "notification_id": "n1",
            "action": "pr",
            "tools": [{"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "revisions": ["68386e630362"]}],
        },
        {"notification_id": "n2", "action": "pr", "tools": [new_entry]},
        {
            "notification_id": "n3",
            "action": "pr",
            "tools": [{"name": "regex_find_replace", "owner": "jjohnson", "revisions": ["9ea374bb0350"]}],
        },
        # Issue items wait for the admins.
        {
            "notification_id": "n4",
            "action": "issue",
            "tools": [{"name": "bwa", "owner": "devteam", "revisions": ["4a196b9c72c2"]}],
        },
    ]

    tools_file = tmp_path / "tools.yaml"
    tools_file.write_text(yaml.safe_dump(existing))

    merged = _render_yaml(monkeypatch, items, tools_file)
    # It names the requests whose tools it added, so that only their requesters are told.
    assert capsys.readouterr().out.split() == ["n1", "n2"]

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
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("tools", ["", "# Requested tools\n", "tools:\n", "install_resolver_dependencies: true\r\n"])
def test_render_yaml_leaves_a_tool_list_alone_without_new_tools(tmp_path, monkeypatch, tools):
    tools_file = tmp_path / "tools.yaml"
    tools_file.write_bytes(tools.encode())
    _render_yaml(monkeypatch, [], tools_file)
    assert tools_file.read_bytes() == tools.encode()


def test_render_yaml_starts_a_tool_list_that_installs_dependencies(tmp_path, monkeypatch):
    items = [{"notification_id": "n1", "action": "pr", "tools": [{"name": "fastp", "owner": "iuc"}]}]

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
            "notification_id": "n1",
            "action": "pr",
            "tools": [
                {"name": "null_revisions", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "no_revisions", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "changeset_pin", "owner": "o", "revisions": ["68386e630362"]},
                {"name": "numeric", "owner": "o", "revisions": ["123456789012"]},
            ],
        }
    ]

    assert merge_tool_list(existing, items)[0]["tools"] == [
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
            "notification_id": "n1",
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

    assert reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/pull/7")

    [(url, payload)] = posted
    assert url == "http://galaxy.test/api/notifications"
    assert payload["recipients"]["user_ids"] == ["u2"]
    assert payload["notification"]["content"]["category"] == "message"
    # Galaxy stores up to 32 characters, and fails to send a notification with a longer source.
    assert len(payload["notification"]["source"]) <= 32
    assert "https://github.com/org/tools/pull/7" in payload["notification"]["content"]["message"]

    # A requester whose account is gone cannot be answered, which must not stop the run.
    assert not reply(gi, ["b887d74393f85b6d"], "https://github.com/org/tools/issues/8")
    assert len(posted) == 1

    # Several requests, also from the same requester, get one notification, which counts once against Galaxy's
    # limit of notifications per minute.
    assert reply(
        gi, ["b2486a20bc56b90f", "0aab0e4c25198ad8", "b887d74393f85b6d"], "https://github.com/org/tools/pull/7"
    )
    assert len(posted) == 2
    assert posted[-1][1]["recipients"]["user_ids"] == ["u2"]

    # Galaxy sends nothing to users who turned message notifications off.
    sent.count = 0
    assert not reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/pull/7")


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
    assert main(["reply", "b2486a20bc56b90f", "--url", "https://github.com/org/tools/pull/7"]) == 1
    assert "Could not tell the requesters of b2486a20bc56b90f" in caplog.text


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
    assert reply(gi, ["b2486a20bc56b90f"], state="installed")
    assert posted[-1]["subject"] == "Your requested tools are installed"
    assert "http" not in posted[-1]["message"]
    assert reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/issues/8", state="closed")
    assert posted[-1]["message"].endswith(": https://github.com/org/tools/issues/8")
    # Galaxy deletes requests some months after they were sent.
    assert not reply(gi, ["0000000000000000"], state="closed")
    assert len(posted) == 2


def test_installed_checks_the_tools_galaxy_loaded():
    def galaxy(*tool_ids):
        def get(url, params=None):
            assert (url, params) == ("http://galaxy.test/api/tools", {"in_panel": False})
            return SimpleNamespace(
                json=lambda: [{"id": i} for i in ("upload1", *tool_ids)], raise_for_status=lambda: None
            )

        return SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)

    fastp = {"name": "fastp", "owner": "iuc", "tool_shed_url": SHED, "revisions": ["68386e630362"]}
    items = [
        {"notification_id": "n1", "action": "pr", "tools": [fastp], "tool_ids": [FASTP_ID]},
        # Issue items do not pin every tool, so an admin decides.
        {"notification_id": "n2", "action": "issue", "tools": [fastp], "tool_ids": [FASTP_ID]},
        # A revision without tools, such as a suite, cannot be checked.
        {"notification_id": "n3", "action": "pr", "tools": [fastp], "tool_ids": []},
    ]

    # The id holds the Tool Shed, owner, repository, tool and version, so another revision with the same version
    # counts, and the same tool from another owner or Tool Shed does not.
    assert installed(galaxy(FASTP_ID), items) == ["n1"]
    assert installed(galaxy(FASTP_ID.replace("galaxy0", "galaxy1")), items) == []
    assert installed(galaxy(FASTP_ID.replace("/iuc/", "/other/")), items) == []
    assert installed(galaxy(), items) == []


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
    assert reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/pull/7")
    # The request then stays unseen, so that the next run answers it.
    task.id = "t2"
    with pytest.raises(ReplyFailed):
        reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/pull/7")
    # Not sent in time counts as not sent, so it is asked again, even if Galaxy may send it later.
    monkeypatch.setattr(tool_request_consumer, "REPLY_TIMEOUT", -1)
    task.id = "t3"
    with pytest.raises(ReplyFailed):
        reply(gi, ["b2486a20bc56b90f"], "https://github.com/org/tools/pull/7")


def test_emit_reports_galaxy_refusing_it(monkeypatch, caplog):
    def get(url, params=None):
        raise requests.HTTPError("401 Client Error: Unauthorized")

    gi = SimpleNamespace(url="http://galaxy.test/api", make_get_request=get)
    monkeypatch.setattr(tool_request_consumer, "get_galaxy_connection", lambda args, log, login_required: gi)

    assert main(["emit"]) == 1
    assert "Could not read the requests from Galaxy: 401 Client Error" in caplog.text
