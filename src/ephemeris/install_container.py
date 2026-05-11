"""
Install or tabulate (singularity) containers

Use cases:

1. run on the Galaxy machine itself and trigger caching of (singularity) containers
2. determine a table that maps docker URIs and cached container image paths.
   this table can then be used on machines that do not have access to CVMFS
   to download container images.

what the tool does:

1. query the list of tools from an instance (optionaly filter by regexes on the tool_ids and latest version)
2. for each tool:

- resolve the container with the container resolvers that are configured at the target instance
  (for cached singularity containers with a configured cache directory this will yield a path)
- if `--install_container` the resolver(s) will be called again with the install parameter set to `True`
  (if the determined path does not exist)
- if `--tabulate` is used the tool ids and the result of the container resolvers (the cached path)
  will be printed comma separated
  if in addition `--index N` is used the `N`-th configured resolver is called and the result is printed as additional
  column. The idea is that the instance configures a singularity container resolver (at index N) without a cache
  directory defined. This resolver will yield the original container URI (docker://...). If this resolver
  is defined after the cached / non-cached singularity container resolvers it will never be called in production.
"""

import argparse
import logging
import os
import os.path
import re
from typing import (
    Any,
    List,
    TYPE_CHECKING,
)

from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.container_resolution import ContainerResolutionClient
from bioblend.galaxy.tools import ToolClient
from galaxy.tool_util.version import parse_version
from galaxy.util.tool_version import remove_version_from_guid

if TYPE_CHECKING:
    from packaging.version import (
        LegacyVersion,
        Version,
    )


def get_tool_list(galaxy_instance: GalaxyInstance, include: List[str], exclude: List[str], latest: bool) -> list[str]:
    """
    get a list of tool IDs from a galaxy instance

    include are applied and if desired only the latest version of each tool is returned
    """
    tool_client = ToolClient(galaxy_instance)
    tools = tool_client.get_tools()

    tool_versions: dict[str, list[tuple[LegacyVersion | Version, Any]]] = {}
    for tool in tools:
        tool_id = tool["id"]
        if include and not any([re.search(f, tool_id) for f in include]):
            continue
        if exclude and any([re.search(f, tool_id) for f in exclude]):
            continue
        tool_id = remove_version_from_guid(tool_id) or tool_id

        if tool_id not in tool_versions:
            tool_versions[tool_id] = []
        try:
            version = parse_version(tool["version"])
        except Exception:
            logger.error(f"could not parse version {version} of tool {tool}")
            continue
        tool_versions[tool_id].append((version, tool["id"]))
    tool_list = []
    for tool_id in tool_versions:
        tool_versions[tool_id] = sorted(tool_versions[tool_id], reverse=True)
        if latest:
            tool_versions[tool_id] = tool_versions[tool_id][:1]
        for t in tool_versions[tool_id]:
            tool_list.append(t[1])
    return tool_list


parser = argparse.ArgumentParser(description="List / install containers")
parser.add_argument("--url", type=str, action="store", required=True, default=None, help="Galaxy URL")
parser.add_argument(
    "--key", type=str, action="store", required=False, default=None, help="API key, better set API_KEY env var"
)
parser.add_argument(
    "--include",
    type=str,
    action="append",
    dest="include",
    default=[],
    help="include tool id by searching for regexp, if any filter applies a tool is included",
)
parser.add_argument(
    "--exclude",
    type=str,
    action="append",
    dest="exclude",
    default=[],
    help="filter tool id by searching for regexp, if any filter applies a tool is excluded",
)
parser.add_argument("--latest", action="store_true", default=False, help="consider only the latest version of the tool")
parser.add_argument("--install_container", action="store_true", default=False, help="install the container")
parser.add_argument("--tabulate", action="store_true", default=False, help="Tabulate tool_id and resolver results")
parser.add_argument(
    "--index",
    type=int,
    action="store",
    required=False,
    default=None,
    help="The index of an additional resolver to tabulate",
)
parser.add_argument(
    "-log",
    "--loglevel",
    choices=["debug", "info", "warning", "error"],
    default="warning",
    help="Provide logging level. Example --loglevel debug, default=warning",
)
args = parser.parse_args()

logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
# Set the log level for your logger to the desired level (e.g., INFO)
logger.setLevel(args.loglevel.upper())

# Create a handler for logging output (e.g., console handler)
handler = logging.StreamHandler()
logger.addHandler(handler)

# Add a formatter to the handler (optional)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

key = os.environ.get("GALAXY_API_KEY", args.key)
galaxy_instance = GalaxyInstance(url=args.url, key=key)

# get tools (matching filters and latest arguments)
tool_list = get_tool_list(galaxy_instance, args.include, args.exclude, args.latest)

container_resolution_client = ContainerResolutionClient(galaxy_instance=galaxy_instance)

for tool in tool_list:
    logger.debug(f"Checking {tool}")
    res = container_resolution_client.resolve_toolbox(tool_ids=[tool])
    container = None
    for i, r in enumerate(res):
        logger.debug(f"{r=}")
        tool_id = r["tool_id"]
        container = r["status"].get("environment_path")

    if container is None:
        logger.debug(f"No container for for {tool}")
        continue

    if args.tabulate:
        if args.index is None:
            print(f"{tool}\t{container}")
        else:
            res = container_resolution_client.resolve_toolbox(tool_ids=[tool], index=args.index)
            container_uri = None
            for i, r in enumerate(res):
                logger.debug(f"{r=}")
                tool_id = r["tool_id"]
                container_uri = r["status"].get("environment_path")
            print(f"{tool}\t{container}\t{container_uri}")

    if args.install_container:
        if os.path.exists(container):
            logger.debug(f"Container for {tool} already installed {os.path.basename(container)}")
            continue

        res = container_resolution_client.resolve_toolbox(tool_ids=[tool], install=args.install_container)
        for i, r in enumerate(res):
            tool_id = r["tool_id"]
            new_container = r["status"].get("environment_path")

            if new_container and os.path.exists(new_container):
                print(f"Installed {new_container}")
            else:
                logger.error(f"Could not install container for {tool} {container=} {new_container=}")
