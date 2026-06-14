from collections.abc import Iterable
from typing import TYPE_CHECKING

from bioblend.toolshed import ToolShedInstance

if TYPE_CHECKING:
    from .shed_tools import InstallRepoDict


VALID_KEYS = [
    "name",
    "owner",
    "changeset_revision",
    "tool_panel_section_id",
    "tool_panel_section_label",
    "tool_shed_url",
    "install_repository_dependencies",
    "install_resolver_dependencies",
    "install_tool_dependencies",
]


def complete_repo_information(
    tool: "InstallRepoDict",
    default_toolshed_url: str,
    default_install_tool_dependencies: bool,
    default_install_repository_dependencies: bool,
    default_install_resolver_dependencies: bool,
    force_latest_revision,
) -> "InstallRepoDict":
    tool["tool_shed_url"] = format_tool_shed_url(tool.get("tool_shed_url") or default_toolshed_url)
    tool = get_changeset_revisions(tool, force_latest_revision=force_latest_revision)
    repo: InstallRepoDict = dict(
        name=tool["name"],
        owner=tool["owner"],
        tool_shed_url=tool["tool_shed_url"],
        changeset_revision=tool.get("changeset_revision"),
        install_repository_dependencies=tool.get("install_repository_dependencies")
        or default_install_repository_dependencies,
        install_resolver_dependencies=tool.get("install_resolver_dependencies")
        or default_install_resolver_dependencies,
        install_tool_dependencies=tool.get("install_tool_dependencies") or default_install_tool_dependencies,
    )
    # We need those values. Throw a KeyError when not present
    tool_panel_section_label = tool.get("tool_panel_section_label")
    if tool_panel_section_label:
        repo["tool_panel_section_label"] = tool_panel_section_label
    else:
        repo["tool_panel_section_id"] = tool.get("tool_panel_section_id")

    return repo


def format_tool_shed_url(tool_shed_url: str) -> str:
    formatted_tool_shed_url = tool_shed_url
    if not formatted_tool_shed_url.endswith("/"):
        formatted_tool_shed_url += "/"
    if not formatted_tool_shed_url.startswith("http"):
        formatted_tool_shed_url = "https://" + formatted_tool_shed_url
    return formatted_tool_shed_url


def get_installable_revisions(repository: "InstallRepoDict") -> list[str]:
    """Query the tool shed for the ordered list of installable revisions of a repository.

    ``repository`` must have ``tool_shed_url`` already formatted (see
    :func:`format_tool_shed_url`). Talks only to the Tool Shed, no Galaxy connection.
    """
    ts = ToolShedInstance(url=repository["tool_shed_url"])
    return ts.repositories.get_ordered_installable_revisions(repository["name"], repository["owner"])


def get_changeset_revisions(repository: "InstallRepoDict", force_latest_revision: bool = False):
    """
    Select the correct changeset revision for a repository,
    and make sure the repository exists
    (i.e a request to the tool shed with name and owner returns a list of revisions).
    Return repository or None, if the repository could not be found on the specified tool shed.
    """
    # Do not connect to the internet when not necessary
    if repository.get("changeset_revision") is None or force_latest_revision:
        # Get the set revision or set it to the latest installable revision
        installable_revisions = get_installable_revisions(repository)
        if not installable_revisions:  #
            raise LookupError(f"Repo does not exist in tool shed: {repository}")
        repository["changeset_revision"] = installable_revisions[-1]

    return repository


def validate_against_tool_shed(
    repositories: Iterable[dict],
    default_toolshed_url: str,
    log=None,
) -> list[str]:
    """Check each repository (and every pinned changeset revision) against the Tool Shed.

    Requires no Galaxy connection. Returns a list of human-readable error messages,
    empty when every repository exists and all pinned revisions are installable. Each
    repository is queried once; both ``revisions`` (list) and a single
    ``changeset_revision`` are checked for membership in the installable revisions.
    """
    errors: list[str] = []
    for repo_info in repositories:
        repo: InstallRepoDict = dict(repo_info)  # type: ignore[assignment]
        tool_shed_url = format_tool_shed_url(repo.get("tool_shed_url") or default_toolshed_url)
        repo["tool_shed_url"] = tool_shed_url
        name = repo["name"]
        owner = repo["owner"]
        label = f"{owner}/{name}"
        pinned_revisions = list(repo.get("revisions") or [])
        changeset_revision = repo.get("changeset_revision")
        if changeset_revision:
            pinned_revisions.append(changeset_revision)
        try:
            installable_revisions = get_installable_revisions(repo)
        except Exception as e:
            errors.append(f"{label}: failed to query tool shed {tool_shed_url}: {e}")
            continue
        if not installable_revisions:
            errors.append(f"{label}: repository does not exist on tool shed {tool_shed_url}")
            continue
        for revision in pinned_revisions:
            if revision not in installable_revisions:
                errors.append(
                    f"{label}: changeset_revision '{revision}' is not installable on {tool_shed_url} "
                    f"(installable revisions: {', '.join(installable_revisions)})"
                )
    if log:
        for error in errors:
            log.error(error)
    return errors


def flatten_repo_info(
    repositories: Iterable["InstallRepoDict"],
) -> list["InstallRepoDict"]:
    """
    Flatten the dict containing info about what tools to install.
    The tool definition YAML file allows multiple revisions to be listed for
    the same tool. To enable simple, iterative processing of the info in this
    script, flatten the `tools_info` list to include one entry per tool revision.

    :type repositories: list of dicts
    :param repositories: Each dict in this list should contain info about a tool.
    :rtype: list of dicts
    :return: Return a list of dicts that correspond to the input argument such
             that if an input element contained `revisions` key with multiple
             values, those will be returned as separate list items.
    """

    flattened_list: list[InstallRepoDict] = []
    for repo_info in repositories:
        new_repo_info = repo_info.copy()
        if "revisions" in new_repo_info:
            revisions = new_repo_info.pop("revisions")
            if not revisions:  # Revisions are empty list or None
                flattened_list.append(new_repo_info)
            else:
                for revision in revisions:
                    # A new dictionary must be created, otherwise there will
                    # be aliasing of dictionaries. Which leads to multiple
                    # repos with the same revision in the end result.
                    new_revision_dict = new_repo_info.copy()
                    new_revision_dict["changeset_revision"] = revision
                    flattened_list.append(new_revision_dict)
        else:  # Revision was not defined at all
            flattened_list.append(new_repo_info)
    return flattened_list
