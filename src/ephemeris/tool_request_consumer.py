#!/usr/bin/env python
"""Turn Galaxy tool installation requests into work for a tool-list repository.

Users ask for tools through Galaxy's tool installation request form or from a
workflow that misses tools, and every admin receives a
``tool_installation_request`` notification. With an admin API key, these
subcommands read the requests, resolve their tools on the Tool Shed, add them
to a tool list, and tell the requester. A request that pins a version of every
tool, each found in an installable revision on the Tool Shed, becomes a ``pr``
work item; everything else an ``issue``, for an admin to judge.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from functools import cache

import requests
import yaml
from bioblend import ConnectionError as BioblendError
from bioblend.toolshed import ToolShedInstance

from . import (
    get_galaxy_connection,
    load_yaml_file,
)
from .common_parser import (
    add_log_file_argument,
    add_verbosity_argument,
    get_common_args,
    HideUnderscoresHelpFormatter,
)
from .ephemeris_log import (
    disable_external_library_logging,
    setup_global_logger,
)
from .shed_tools_methods import format_tool_shed_url

CATEGORY = "tool_installation_request"
DEFAULT_TOOL_SHED = "https://toolshed.g2.bx.psu.edu/"
DEFAULT_PANEL_LABEL = "Tools from user request"
# Seconds to wait for each response from the Tool Shed or Galaxy.
TIMEOUT = 60
TOOL_SHED_ERRORS = (BioblendError, OSError, ValueError)
# Seconds to wait for a Galaxy that sends notifications in a Celery task.
REPLY_TIMEOUT = 60
# How a tool list that render-yaml starts installs its tools.
NEW_TOOL_LIST = {
    "install_repository_dependencies": True,
    "install_resolver_dependencies": True,
}
# Subject, message, and what the link in the message points to, for each state of a request.
REPLIES = {
    "handling": (
        "Your tool installation request",
        "Your tool installation request is being handled.",
        "You can follow it here",
    ),
    "installed": (
        "Your requested tools are installed",
        "The tools you asked for are installed now.",
        "More about your request",
    ),
    "closed": (
        "Your tool installation request was closed",
        "Your tool installation request was closed without installing the tools.",
        "More about it",
    ),
}
# The characters the Tool Shed allows in repository names.
REPOSITORY_NAME = re.compile(r"[a-z0-9_]+")

log = logging.getLogger(__name__)


class Unresolved(Exception):
    pass


class ReplyFailed(Exception):
    pass


def select_requests(notifications: list[dict]) -> list[dict]:
    """Keep the unseen tool installation requests in an admin's notifications.

    Submitters get their confirmation copy in their own inbox, so an admin's inbox
    only holds the requests themselves.
    """
    return [n for n in notifications if n.get("category") == CATEGORY and not n.get("seen_time")]


@cache
def _shed(url: str) -> ToolShedInstance:
    shed = ToolShedInstance(url=url)
    shed.timeout = TIMEOUT
    return shed


@cache
def _repositories(shed_url: str, name: str, owner: str | None = None) -> list[dict]:
    return _shed(shed_url).repositories.get_repositories(name=name, owner=owner)


@cache
def _installable_revisions(shed_url: str, repository_id: str) -> list[dict]:
    shed = _shed(shed_url)
    response = shed.make_get_request(
        f"{shed.url}/repositories/{repository_id}/metadata", params={"downloadable_only": True}
    )
    response.raise_for_status()
    return list(response.json().values())


def _find_repository(shed_url: str, name: str | None) -> dict:
    """Find the repository named exactly like a free-text tool name."""
    if not name:
        raise Unresolved("no tool name to look the repository up by")
    # An exact lookup is fast whatever users type, unlike the Tool Shed's full-text search. Repository
    # names only hold lower case letters, digits and underscores, so try the name in that form too.
    typed = name.strip().lower()
    keys = [
        k for k in dict.fromkeys([typed, re.sub(r"[^a-z0-9]+", "_", typed).strip("_")]) if REPOSITORY_NAME.fullmatch(k)
    ]
    matches = next((found for found in (_repositories(shed_url, key) for key in keys) if found), [])
    if not matches:
        raise Unresolved(f"no repository named {name} on {shed_url}")
    if len(matches) > 1:
        raise Unresolved(
            "several repositories match: " + ", ".join(sorted(f"{r['owner']}/{r['name']}" for r in matches))
        )
    return matches[0]


def _find_revision(
    shed_url: str, repository: dict, version: str | None, tool_id: str | None
) -> tuple[str, list[tuple[str, str]]]:
    """Return the newest installable revision that ships the requested tool version, and the ids and versions of
    the tools requested from it.

    Without a version, return the newest revision that ships the tool, or the newest
    revision and all of its tools if no tool is named.
    """
    # Legacy revisions can lack a numeric revision.
    revisions = sorted(
        _installable_revisions(shed_url, repository["id"]),
        key=lambda r: -1 if r["numeric_revision"] is None else r["numeric_revision"],
        reverse=True,
    )
    if tool_id is None and version is not None:
        # A free-text request names the repository, so its version is that of the tool named like it, or of its
        # only tool. Several tools could each have that version.
        tool_ids = _tool_ids(revisions)
        if repository["name"] in tool_ids:
            tool_id = repository["name"]
        elif len(tool_ids) > 1:
            raise Unresolved(f"{repository['name']} has several tools, so the version does not tell which one")
    for revision in revisions:
        tools = [(tool["id"], tool["version"]) for tool in revision.get("tools", [])]
        if version is None and tool_id is None:
            return revision["changeset_revision"], tools
        for found in tools:
            if version in (None, found[1]) and tool_id in (None, found[0]):
                return revision["changeset_revision"], [found]
    raise Unresolved(f"no installable revision has version {version}" if version else "no installable revision")


def _tool_ids(revisions: list[dict]) -> set[str]:
    return {tool["id"] for revision in revisions for tool in revision.get("tools", [])}


def _without_scheme(url: str) -> str:
    return re.sub(r"^https?://", "", url, flags=re.IGNORECASE).rstrip("/").lower()


def _resolve(tool: dict, shed_url: str, pin_latest: bool = False) -> tuple[str, str, str | None, list[str]]:
    """Return the owner, repository name and pinned revision of a requested tool, and the ids Galaxy gives the
    requested tools of that revision.

    All of them are spelled as the Tool Shed does. Without ``pin_latest``, a tool
    requested without a version is not pinned, and has no ids.
    """
    tool_id = None
    if tool.get("tool_shed_id"):
        # Workflow requests name the repository as <shed>/repos/<owner>/<name> and the tool by id.
        host, _, path = tool["tool_shed_id"].partition("/repos/")
        owner, _, name = path.partition("/")
        if not (owner and name):
            raise Unresolved(f"cannot parse Tool Shed id {tool['tool_shed_id']}")
        # Users choose the workflow, so only look tools up on the Tool Shed the admins chose.
        if _without_scheme(host) != _without_scheme(shed_url):
            raise Unresolved(f"{host} is not {shed_url}")
        repositories = _repositories(shed_url, name, owner)
        if not repositories:
            raise Unresolved(f"{owner}/{name} is not on {shed_url}")
        repository = repositories[0]
        tool_id = tool.get("name")
    else:
        repository = _find_repository(shed_url, tool.get("name"))
    owner, name = repository["owner"], repository["name"]
    if not (tool.get("requested_version") or pin_latest):
        return owner, name, None, []
    revision, tools = _find_revision(shed_url, repository, tool.get("requested_version"), tool_id)
    # Galaxy ids Tool Shed tools as <shed>/repos/<owner>/<name>/<tool id>/<version>.
    return owner, name, revision, [f"{_without_scheme(shed_url)}/repos/{owner}/{name}/{i}/{v}" for i, v in tools]


def _label(tool: dict) -> str:
    name = tool.get("name") or tool.get("tool_shed_id") or tool.get("tool_url") or "unnamed tool"
    return " ".join(filter(None, [name, tool.get("requested_version")]))


def emit_item(
    notification: dict,
    tool_shed_url: str,
    panel_label: str,
    label_map: dict | None = None,
    pin_latest: bool = False,
) -> dict:
    """Turn a request into a work item.

    Its ``tools`` are tool list entries for the requested tools that resolved, ``tool_ids`` the ids Galaxy gives
    the pinned tools once installed, and ``unresolved`` says why other tools did not resolve. Tool Shed failures
    propagate, so that the request can be tried again later. With ``pin_latest``, tools requested without a
    version are pinned to their newest installable revision.
    """
    entries: dict[tuple[str, str, bool], dict] = {}
    tool_ids: list[str] = []
    unresolved = []
    for tool in notification["content"]["tools"]:
        if notification["content"].get("workflow_id") and not tool.get("tool_shed_id"):
            # A workflow names its local tools by id, which may match an unrelated repository's name.
            unresolved.append(f"{_label(tool)}: a tool of the workflow that is not from a Tool Shed")
            continue
        try:
            owner, name, revision, ids = _resolve(tool, tool_shed_url, pin_latest)
        except Unresolved as e:
            unresolved.append(f"{_label(tool)}: {e}")
            continue
        # A tool without a version follows the latest revision, so it needs an entry without revisions.
        entry = entries.setdefault(
            (owner, name, revision is None),
            {
                "name": name,
                "owner": owner,
                "tool_shed_url": tool_shed_url,
                "tool_panel_section_label": (label_map or {}).get(f"{owner}/{name}", panel_label),
            },
        )
        if revision and revision not in entry.setdefault("revisions", []):
            entry["revisions"].append(revision)
        tool_ids += ids
    # Only requests that pin every tool to an installable revision skip the admins' judgement.
    pinned = entries and not unresolved and not any(unpinned for _, _, unpinned in entries)
    return {
        "notification_id": notification["id"],
        "action": "pr" if pinned else "issue",
        "tools": list(entries.values()),
        "tool_ids": list(dict.fromkeys(tool_ids)),
        "unresolved": unresolved,
    }


def emit(
    notifications: list[dict],
    tool_shed_url: str,
    panel_label: str,
    label_map: dict | None = None,
    pin_latest: bool = False,
) -> list[dict]:
    """Turn requests into work items, leaving those the Tool Shed fails to answer for the next run."""
    items = []
    for notification in notifications:
        try:
            items.append(emit_item(notification, tool_shed_url, panel_label, label_map, pin_latest))
        except TOOL_SHED_ERRORS as e:
            log.warning(f"Skipping {notification['id']} until the Tool Shed answers: {e}")
            if isinstance(e, requests.ConnectionError):
                log.warning("Skipping the other requests too, since the Tool Shed cannot be reached")
                break
    return items


def _repository_key(entry: dict) -> tuple[str, str, str]:
    return _without_scheme(entry.get("tool_shed_url") or DEFAULT_TOOL_SHED), entry["owner"], entry["name"]


def _pinned_revisions(entry: dict) -> list:
    return entry.get("revisions") or ([entry["changeset_revision"]] if entry.get("changeset_revision") else [])


def merge_tool_list(existing: dict | None, items: list[dict]) -> tuple[dict, list[str]]:
    """Add the tools of ``pr`` items to a tool list, extending the revisions of repositories already listed.

    Return the tool list, and the notification ids of the items whose tools it added.
    Like shed-tools, an entry pins the revisions in ``revisions``, or else the one in
    ``changeset_revision``, and follows the latest revision without either. A
    repository with an entry that follows the latest revision is left alone, and a
    ``changeset_revision`` pin that gains revisions becomes a ``revisions`` list.
    """
    # shed-tools only installs the dependencies of tools when the tool list asks for them.
    merged: dict = dict(existing) if existing is not None else dict(NEW_TOOL_LIST)
    tools = [dict(t) for t in merged.get("tools") or []]
    by_repository: dict[tuple[str, str, str], list[dict]] = {}
    for tool in tools:
        by_repository.setdefault(_repository_key(tool), []).append(tool)
    added = []
    # Issue items wait for the admins' judgement.
    for item in (i for i in items if i["action"] == "pr"):
        changed = False
        for entry in item["tools"]:
            listed = by_repository.setdefault(_repository_key(entry), [])
            if not listed:
                listed.append(dict(entry))
                tools.append(listed[-1])
                changed = True
                continue
            pins = [_pinned_revisions(t) for t in listed]
            if not all(pins):
                continue
            # YAML loads unquoted revisions made of digits as numbers.
            known = {str(r) for pin in pins for r in pin}
            new = [r for r in entry.get("revisions", []) if r not in known]
            if new:
                listed[-1]["revisions"] = list(pins[-1]) + new
                listed[-1].pop("changeset_revision", None)
                changed = True
        if changed:
            added.append(item["notification_id"])
    merged["tools"] = tools
    return merged, added


def fetch_notifications(gi) -> list[dict]:
    """Read all of the user's notifications."""
    # Galaxy does not order this list, so paging through it could miss notifications. A limit of 0 returns all.
    response = gi.make_get_request(f"{gi.url}/notifications", params={"limit": 0})
    response.raise_for_status()
    return response.json()


def _notification(gi, notification_id: str) -> dict | None:
    response = gi.make_get_request(f"{gi.url}/notifications/{notification_id}")
    if response.status_code == 404:
        # Galaxy deletes notifications some months after they were sent.
        return None
    response.raise_for_status()
    return response.json()


def reply(gi, notification_ids: list[str], url: str | None = None, state: str = "handling") -> bool:
    """Tell the requesters of these requests how their requests go, in one notification, see ``REPLIES``.

    One notification counts once against Galaxy's limit of notifications an account
    may send per minute. Return False if nobody could be told: the requests expired,
    or the requesters' accounts are gone or they turned messages off.
    """
    user_ids = []
    for notification_id in notification_ids:
        notification = _notification(gi, notification_id)
        email = notification and notification["content"].get("requester_email")
        if email:
            # The f_email filter matches substrings.
            user_ids += [u["id"] for u in gi.users.get_users(f_email=email) if u["email"].lower() == email.lower()]
    if not user_ids:
        return False
    response = gi.make_post_request(
        f"{gi.url}/notifications",
        payload={
            "recipients": {"user_ids": list(dict.fromkeys(user_ids))},
            "notification": {
                # Galaxy stores up to 32 characters.
                "source": "tool_installation_request_reply",
                "category": "message",
                "variant": "info",
                "content": {"category": "message", "subject": REPLIES[state][0], "message": _reply_text(state, url)},
            },
        },
    )
    if "total_notifications_sent" in response:
        # Galaxy skips users who turned message notifications off.
        return response["total_notifications_sent"] > 0
    # With Celery, Galaxy answers before it sends, so only the task tells whether sending worked.
    _wait_for_task(gi, response["id"])
    return True


def _wait_for_task(gi, task_id: str) -> None:
    deadline = time.monotonic() + REPLY_TIMEOUT
    while True:
        response = gi.make_get_request(f"{gi.url}/tasks/{task_id}/state")
        response.raise_for_status()
        state = response.json()
        if state == "SUCCESS":
            return
        if state == "FAILURE":
            raise ReplyFailed(f"Galaxy failed to send the reply, see its log for task {task_id}")
        if time.monotonic() > deadline:
            # Unknown counts as not sent, so it is asked again: the requester may get the message twice.
            raise ReplyFailed(
                f"Galaxy has not sent the reply within {REPLY_TIMEOUT} seconds, see its log for task {task_id}"
            )
        time.sleep(1)


def _reply_text(state: str, url: str | None) -> str:
    return REPLIES[state][1] + (f" {REPLIES[state][2]}: {url}" if url else "")


def installed(gi, items: list[dict]) -> list[str]:
    """Return the notification ids of the ``pr`` items whose tools Galaxy has loaded, in the requested versions.

    Only ``pr`` items pin every requested tool, so issue items are left to the admins.
    """
    response = gi.make_get_request(f"{gi.url}/tools", params={"in_panel": False})
    response.raise_for_status()
    loaded = {tool["id"] for tool in response.json()}
    return [
        item["notification_id"]
        for item in items
        if item["action"] == "pr" and item["tool_ids"] and loaded.issuperset(item["tool_ids"])
    ]


def mark_seen(gi, notification_ids: list[str]) -> None:
    gi.make_put_request(
        f"{gi.url}/notifications", payload={"notification_ids": notification_ids, "changes": {"seen": True}}
    )


def _parser():
    parser = argparse.ArgumentParser(
        description="Turn Galaxy tool installation requests into work for a tool list repository.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    galaxy_arguments = get_common_args(log_file=True)

    emit = subparsers.add_parser(
        "emit",
        parents=[galaxy_arguments],
        formatter_class=HideUnderscoresHelpFormatter,
        help="Print a JSON list of work items for the unseen requests.",
    )
    emit.add_argument("--tool-shed-url", default=DEFAULT_TOOL_SHED, help="Tool Shed to look requested tools up on.")
    emit.add_argument(
        "--pin-latest",
        action="store_true",
        help="Pin tools requested without a version to their newest installable revision, so that such requests "
        "can become pull request items too.",
    )
    emit.add_argument(
        "-l",
        "--panel-label",
        default=DEFAULT_PANEL_LABEL,
        help="Tool panel section label for requested tools.",
    )
    emit.add_argument(
        "-j",
        "--json-panel-label-suggestion",
        dest="panel_label_json",
        help="JSON file or URL mapping 'owner/name' to a tool panel section label, overriding -l.",
    )

    # render-yaml needs no Galaxy.
    render = subparsers.add_parser(
        "render-yaml",
        formatter_class=HideUnderscoresHelpFormatter,
        help="Merge the tools of the pr work items on stdin into a tool list.",
    )
    add_verbosity_argument(render)
    add_log_file_argument(render)
    render.add_argument("--tools-file", help="Tool list to merge into.")
    render.add_argument(
        "-o",
        "--output",
        help="Where to write the tool list (default: stdout). Then the notification ids of the items whose tools "
        "were added are printed, one per line.",
    )

    reply = subparsers.add_parser(
        "reply",
        parents=[galaxy_arguments],
        formatter_class=HideUnderscoresHelpFormatter,
        help="Tell the requesters of requests where they are handled, or how they ended, in one notification.",
    )
    reply.add_argument("notification_ids", nargs="+", metavar="notification_id", help="Requests to answer.")
    reply.add_argument("--url", help="Issue or pull request URL, required for --state handling.")
    reply.add_argument(
        "--state",
        choices=list(REPLIES),
        default="handling",
        help="What to tell: where the request is handled, that its tools are installed, or that it was closed "
        "without installing them.",
    )

    subparsers.add_parser(
        "installed",
        parents=[galaxy_arguments],
        formatter_class=HideUnderscoresHelpFormatter,
        help="Print the notification ids of the pr work items on stdin whose tools Galaxy has loaded.",
    )

    mark_seen = subparsers.add_parser(
        "mark-seen",
        parents=[galaxy_arguments],
        formatter_class=HideUnderscoresHelpFormatter,
        help="Mark requests as seen, so that emit skips them.",
    )
    mark_seen.add_argument("notification_ids", nargs="+", metavar="notification_id", help="Requests to mark.")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    log = setup_global_logger(__name__, log_file=args.log_file, verbose=args.verbose)
    disable_external_library_logging()

    if args.command == "render-yaml":
        items = json.load(sys.stdin)
        existing = load_yaml_file(args.tools_file) if args.tools_file and os.path.exists(args.tools_file) else None
        merged, added = merge_tool_list(existing, items)
        if not added and args.tools_file and os.path.exists(args.tools_file):
            # Keep the comments, formatting and line endings of a tool list that gains nothing.
            with open(args.tools_file, newline="") as f:
                output = f.read()
        else:
            output = yaml.safe_dump(merged, sort_keys=False)
        if args.output:
            with open(args.output, "w", newline="") as f:
                f.write(output)
            for notification_id in added:
                print(notification_id)
        else:
            sys.stdout.write(output)
        return

    gi = get_galaxy_connection(args, log=log, login_required=True)
    gi.timeout = TIMEOUT
    if args.command == "emit":
        label_map = None
        if args.panel_label_json:
            # Importing it takes long.
            from .generate_tool_list_from_ga_workflow_files import get_dictionary_from_json

            label_map = get_dictionary_from_json(args.panel_label_json)
        try:
            notifications = fetch_notifications(gi)
        except (BioblendError, OSError) as e:
            log.error(f"Could not read the requests from Galaxy: {e}")
            return 1
        pending = select_requests(notifications)
        shed_url = format_tool_shed_url(args.tool_shed_url)
        items = emit(pending, shed_url, args.panel_label, label_map, args.pin_latest)
        for item in items:
            log.info(f"{item['notification_id']}: {item['action']} {', '.join(item['unresolved'])}")
        json.dump(items, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif args.command == "reply":
        if args.state == "handling" and not args.url:
            log.error("--state handling needs --url")
            return 2
        try:
            sent = reply(gi, args.notification_ids, args.url, args.state)
        except (ReplyFailed, BioblendError, OSError) as e:
            # For example, Galaxy limits how many notifications an account may send per minute.
            log.error(f"Could not tell the requesters of {' '.join(args.notification_ids)}: {e}")
            return 1
        if not sent:
            log.warning(
                f"The requests {' '.join(args.notification_ids)} expired, or their requesters have no Galaxy account "
                "anymore or turned messages off, so they were not told"
            )
    elif args.command == "installed":
        try:
            done = installed(gi, json.load(sys.stdin))
        except (BioblendError, OSError) as e:
            log.error(f"Could not check which tools Galaxy has installed: {e}")
            return 1
        for notification_id in done:
            print(notification_id)
    elif args.command == "mark-seen":
        try:
            mark_seen(gi, args.notification_ids)
        except (BioblendError, OSError) as e:
            log.error(f"Could not mark {' '.join(args.notification_ids)} as seen: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
