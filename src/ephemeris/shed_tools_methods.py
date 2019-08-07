from bioblend.toolshed import ToolShedInstance


VALID_KEYS = [
    "name",
    "owner",
    "changeset_revision",
    "tool_panel_section_id",
    "tool_panel_section_label",
    "tool_shed_url",
    "install_repository_dependencies",
    "install_resolver_dependencies",
    "install_tool_dependencies"
]


def complete_repo_information(tool,
                              default_toolshed_url,
                              require_tool_panel_info,
                              default_install_tool_dependencies,
                              default_install_repository_dependencies,
                              default_install_resolver_dependencies,
                              force_latest_revision):
    repo = dict()
    # We need those values. Throw a KeyError when not present
    repo['name'] = tool['name']
    repo['owner'] = tool['owner']
    repo['tool_panel_section_id'] = tool.get('tool_panel_section_id')
    repo['tool_panel_section_label'] = tool.get('tool_panel_section_label')
    if require_tool_panel_info and repo['tool_panel_section_id'] is None and repo[
            'tool_panel_section_label'] is None and 'data_manager' not in repo.get('name'):
        raise KeyError("Either tool_panel_section_id or tool_panel_section_name must be defined for tool '{0}'.".format(
            repo.get('name')))
    repo['tool_shed_url'] = format_tool_shed_url(tool.get('tool_shed_url', default_toolshed_url))
    repo['changeset_revision'] = tool.get('changeset_revision')
    repo = get_changeset_revisions(repo, force_latest_revision)
    repo['install_repository_dependencies'] = tool.get('install_repository_dependencies',
                                                       default_install_repository_dependencies)
    repo['install_resolver_dependencies'] = tool.get('install_resolver_dependencies',
                                                     default_install_resolver_dependencies)
    repo['install_tool_dependencies'] = tool.get('install_tool_dependencies', default_install_tool_dependencies)
    return repo


def format_tool_shed_url(tool_shed_url):
    formatted_tool_shed_url = tool_shed_url
    if not formatted_tool_shed_url.endswith('/'):
        formatted_tool_shed_url += '/'
    if not formatted_tool_shed_url.startswith('http'):
        formatted_tool_shed_url = 'https://' + formatted_tool_shed_url
    return formatted_tool_shed_url


def get_changeset_revisions(repository, force_latest_revision=False):
    """
    Select the correct changeset revision for a repository,
    and make sure the repository exists
    (i.e a request to the tool shed with name and owner returns a list of revisions).
    Return repository or None, if the repository could not be found on the specified tool shed.
    """
    # Do not connect to the internet when not necessary
    if repository.get('changeset_revision') is None or force_latest_revision:
        ts = ToolShedInstance(url=repository['tool_shed_url'])
        # Get the set revision or set it to the latest installable revision
        installable_revisions = ts.repositories.get_ordered_installable_revisions(repository['name'],
                                                                                  repository['owner'])
        if not installable_revisions:  #
            raise LookupError("Repo does not exist in tool shed: {0}".format(repository))
        repository['changeset_revision'] = installable_revisions[-1]

    return repository


def flatten_repo_info(repositories):
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

    flattened_list = []
    for repo_info in repositories:
        new_repo_info = dict()
        for key, value in repo_info.items():
            if key in VALID_KEYS:
                new_repo_info[key] = value
        if 'revisions' in repo_info:
            revisions = repo_info.get('revisions', [])
            if not revisions:  # Revisions are empty list or None
                flattened_list.append(new_repo_info)
            else:
                for revision in revisions:
                    # A new dictionary must be created, otherwise there will
                    # be aliasing of dictionaries. Which leads to multiple
                    # repos with the same revision in the end result.
                    new_revision_dict = dict(**new_repo_info)
                    new_revision_dict['changeset_revision'] = revision
                    flattened_list.append(new_revision_dict)
        else:  # Revision was not defined at all
            flattened_list.append(new_repo_info)
    return flattened_list
