"""
A script to automate installation of tool repositories from a Galaxy Tool Shed
into an instance of Galaxy.

Shed-tools has two commands: update and install.

Update simply updates all the tools in a Galaxy given connection details on the command line.

Install allows installation of tools in multiple ways.
Galaxy instance details and the installed tools can be provided in one of three
ways:

1. In the YAML format via dedicated files (a sample can be found
   `here <https://github.com/galaxyproject/ansible-galaxy-tools/blob/master/files/tool_list.yaml.sample>`_).
2. On the command line as dedicated script options (see the usage help).
3. As a single composite parameter to the script. The parameter must be a
   single, YAML-formatted string with the keys corresponding to the keys
   available for use in the YAML formatted file (for example:
   `--yaml_tool "{'owner': 'kellrott', 'tool_shed_url':
   'https://testtoolshed.g2.bx.psu.edu', 'tool_panel_section_id':
   'peak_calling', 'name': 'synapse_interface'}"`).

Only one of the methods can be used with each invocation of the script but if
more than one are provided are provided, precedence will correspond to order
of the items in the list above.
When installing tools, Galaxy expects any `tool_panel_section_id` provided when
installing a tool to already exist in the configuration. If the section
does not exist, the tool will be installed outside any section. See
`shed_tool_conf.xml.sample` in this directory for a sample of such file. Before
running this script to install the tools, make sure to place such file into
Galaxy's configuration directory and set Galaxy configuration option
`tool_config_file` to include it.
"""

# Required libraries:
# bioblend, pyyaml

import datetime as dt
import json
import re
import sys
import time
from argparse import ArgumentParser

import yaml
from bioblend.galaxy.client import ConnectionError
from bioblend.galaxy.toolshed import ToolShedClient
from bioblend.toolshed import ToolShedInstance
from galaxy.tools.verify.interactor import GalaxyInteractorApi, verify_tool

from . import get_galaxy_connection, load_yaml_file
from .common_parser import get_common_args
from .ephemeris_log import disable_external_library_logging, setup_global_logger
from .get_tool_list_from_galaxy import GiToToolYaml, tools_for_repository

# If no toolshed is specified for a tool/tool-suite, the Main Tool Shed is taken
MTS = 'https://toolshed.g2.bx.psu.edu/'  # Main Tool Shed

# The behavior of a tool installation and its dependencies can be controlled in a few ways.
# You can add
#   - install_tool_dependencies: True or False          (traditional Tool Shed dependencies)
#   - install_repository_dependencies: True or False    (used for datatypes or suites)
#   - install_resolver_dependencies: True or False      (other Galaxy supported dependency resolvers, like Conda)
# to every tool section in the tool-yaml file or you can add these options to the top of the yaml
# file (next to galaxy_instance or api_key) to set a global default value, which can be overwritten
# later in every section. Not specifying any of these options will use the values below,
# means traditional tool_dependencies will not be installed.
INSTALL_TOOL_DEPENDENCIES = False
INSTALL_REPOSITORY_DEPENDENCIES = True
INSTALL_RESOLVER_DEPENDENCIES = True
EXIT_CODE_INSTALL_ERRORS = 1
EXIT_CODE_TOOL_TEST_ERRORS = 2


def _ensure_log_configured(name):
    # For library-style usage - just ensure a log exists and use ephemeris name.
    if 'log' not in globals():
        global log
        log = setup_global_logger(name)


def log_repository_install_error(repository, start, msg, errored_repositories):
    """
    Log failed tool installations
    """
    _ensure_log_configured(__name__)
    end = dt.datetime.now()
    log.error("\t* Error installing a repository (after %s seconds)! Name: %s," "owner: %s, ""revision: %s, error: %s",
              str(end - start),
              repository.get('name', ""),
              repository.get('owner', ""),
              repository.get('changeset_revision', ""),
              msg)
    errored_repositories.append({
        'name': repository.get('name', ""),
        'owner': repository.get('owner', ""),
        'revision': repository.get('changeset_revision', ""),
        'error': msg})


def log_repository_install_success(repository, start, installed_repositories):
    """
    Log successful repository installation.
    Tools that finish in error still count as successful installs currently.
    """
    _ensure_log_configured(__name__)
    end = dt.datetime.now()
    installed_repositories.append({
        'name': repository['name'],
        'owner': repository['owner'],
        'revision': repository['changeset_revision']})
    log.debug(
        "\trepository %s installed successfully (in %s) at revision %s" % (
            repository['name'],
            str(end - start),
            repository['changeset_revision']
        )
    )


def the_same_repository(repo_1_info, repo_2_info):
    """
    Given two dicts containing info about tools, determine if they are the same
    tool.
    Each of the dicts must have the following keys: `name`, `owner`, and
    (either `tool_shed` or `tool_shed_url`).
    """
    t1ts = repo_1_info.get('tool_shed', repo_1_info.get('tool_shed_url', None))
    t2ts = repo_2_info.get('tool_shed', repo_2_info.get('tool_shed_url', None))

    if repo_1_info.get('name') == repo_2_info.get('name') and \
       repo_1_info.get('owner') == repo_2_info.get('owner') and \
       (t1ts in t2ts or t2ts in t1ts):
        return True
    return False


def installed_repository_revisions(gi, omit=None):
    """
    Get a list of repository revisions installed from a Tool Shed on a Galaxy instance.
    Included are all the repository revisions that were installed from a Tool
    Shed and are available from `/api/tool_shed_repositories` url on the
    given instance of Galaxy.
    :type gi: GalaxyInstance object
    :param gi: A GalaxyInstance object as retured by `galaxy_instance` method.
    :type omit: list of strings
    :param omit: A list of strings that, if found in a tool name, will result
                    in the tool not being included in the returned list.
    :rtype: list of dicts
    :return: Each dict in the returned list will have the following keys:
             `name`, `owner`, `tool_shed_url`, `revisions`.
    .. seealso:: this method returns a subset of data returned by
                 `installed_repositories` function
    """
    if not omit:
        omit = []
    tool_shed_client = ToolShedClient(gi)

    # Create dictionary to look up all tools based on repository information

    installed_revisions_list = []
    installed_repositories_list = tool_shed_client.get_repositories()
    for installed_repository in installed_repositories_list:
        if installed_repository['status'] == 'Installed':
            skip = False
            # Check if we already processed this tool and, if so, add the new
            # revision to the existing list entry
            for installed_revision in installed_revisions_list:
                if the_same_repository(installed_repository, installed_revision):
                    installed_revision['revisions'].append(installed_repository.get('changeset_revision', None))
                    skip = True
            # Check if the repo name is contained in the 'omit' list
            for omitted_repository in omit:
                if omitted_repository in installed_repository['name']:
                    skip = True
            # We have not processed this tool so create a list entry
            if not skip:
                repo_info = {
                    'name': installed_repository['name'],
                    'owner': installed_repository['owner'],
                    'revisions': [installed_repository.get('changeset_revision', None)],
                    'tool_shed_url': 'https://' + installed_repository['tool_shed'],
                }
                installed_revisions_list.append(repo_info)
    return installed_revisions_list


def installed_repositories(gi, omit=None):
    """
    Get a list of repositories on a Galaxy instance.
    :type gi: GalaxyInstance object
    :param gi: A GalaxyInstance object as retured by `galaxy_instance` method.
    :type omit: list of strings
    :param omit: A list of strings that, if found in a repository name, will result
                    in the repository not being included in the returned list.
    :rtype: dict
    :return: The returned dictionary contains the following keys, each
             containing a list of dictionaries:
                - `tool_panel_shed_repositories` with a list of repositories available in the
                tool panel that were installed on the target Galaxy instance
                from the Tool Shed;
                - `tool_panel_custom_tools` with a list of tools available in
                the tool panel that were not installed via the Tool Shed;
                - `shed_repositories` with a list of repositories returned from the
                `installed_repository_revisions` function and complemented with a
                `tool_panel_section_id` key as matched with the list of repositories
                from the first element of the returned triplet. Note that the
                two lists (`shed_repositories` and `tool_panel_shed_repositories`) are likely
                to be different and hence not every element in the `shed_repositories`
                will have the `tool_panel_section_id`!
    .. seealso:: `installed_repository_revisions` (this function also returns the
                 output of the `installed_repository_revisions` function, as
                 `shed_repositories` key).
    """
    if not omit:
        omit = []
    tool_panel_repos = []  # The Tool Shed repositories of tools available in the tool panel and installable via a TS
    custom_tools = []  # Tools available in the tool panel but custom-installed

    panel_tool_list = gi.tools.get_tool_panel()
    for tool_section in panel_tool_list:
        # print "%s (%s): %s" % (ts['name'], ts['id'], len(ts.get('elems', [])))
        # Parse the tool panel to ge the the tool lists
        for panel_tool in tool_section.get('elems', []):
            # Tool ID is either a tool name (in case of custom-installed tools)
            # or a URI (in case of Tool Shed-installed tools) so differentiate
            # among those
            panel_tool_id = panel_tool['id'].split('/')
            if len(panel_tool_id) > 3:
                skip = False
                # Check if we already encountered this tool
                for added_tool in tool_panel_repos:
                    if panel_tool_id[3] in added_tool['name']:
                        skip = True
                # Check if the repo name is contained in the 'omit' list
                for omitted_repo in omit:
                    if omitted_repo in panel_tool_id[3]:
                        skip = True
                if not skip:
                    tool_panel_repos.append(
                        {'tool_shed_url': "https://{0}".format(panel_tool_id[0]),
                         'owner': panel_tool_id[2],
                         'name': panel_tool_id[3],
                         'tool_panel_section_id': tool_section['id']})
            else:
                custom_tools.append(panel_tool['id'])

    # Match tp_tools with the tool list available from the Tool Shed Clients on
    # the given Galaxy instance and and add tool section IDs it
    shed_repositories = installed_repository_revisions(gi, omit)  # Tools revisions installed via a TS
    for shed_tool in shed_repositories:
        for panel_tool in tool_panel_repos:
            if the_same_repository(shed_tool, panel_tool):
                shed_tool['tool_panel_section_id'] = panel_tool['tool_panel_section_id']

    return {'tool_panel_shed_repositories': tool_panel_repos,
            'tool_panel_custom_tools': custom_tools,
            'shed_repositories': shed_repositories}


def _list_repository_categories(repository_dictionaries_list):
    """
    Given a list of dicts `repository_dictionaries_list` as returned by the `installed_repositories` method and
    where each list element holds a key `tool_panel_section_id`, return a list
    of unique section IDs.
    """
    category_list = []
    for repo_dictionary in repository_dictionaries_list:
        category_list.append(repo_dictionary.get('id'))
    return set(category_list)


def _parser():
    """construct the parser object"""
    common_arguments = get_common_args(log_file=True)
    parser = ArgumentParser()
    subparsers = parser.add_subparsers()

    # A list of defaults is needed. Otherwise the shed-tools install parser will not return
    # update_tools in the name space and shed-tool update will not return all the install
    # variables.
    parser.set_defaults(
        action="install",
        tool_list_file=None,
        tool_yaml=None,
        owner=None,
        name=None,
        tool_panel_section_id=None,
        tool_panel_section_label=None,
        revisions=None,
        tool_shed_url=None,
        skip_tool_dependencies=False,
        install_resolver_dependencies=False,
        force_latest_revision=False,
        test=False,
        test_user_api_key=None,
        test_user="ephemeris@galaxyproject.org",
        test_json="tool_test_output.json",
        test_existing=False,
    )
    install_command_parser = subparsers.add_parser(
        "install",
        help="This installs tools in Galaxy from the Tool Shed."
             "Use shed-tools install --help for more information",
        parents=[common_arguments],
    )
    install_command_parser.set_defaults(
        update_tools=False
    )
    update_command_parser = subparsers.add_parser(
        "update",
        help="This updates all tools in Galaxy to the latest revision. "
             "Use shed-tools update --help for more information",
        parents=[common_arguments])

    test_command_parser = subparsers.add_parser(
        "test",
        help="This tests the supplied list of tools in Galaxy. "
             "Use shed-tools test --help for more information",
        parents=[common_arguments])

    for command_parser in [install_command_parser, test_command_parser]:
        command_parser.add_argument(
            "-t", "--toolsfile",
            dest="tool_list_file",
            help="Tools file to use (see tool_list.yaml.sample)",)
        command_parser.add_argument(
            "-y", "--yaml_tool",
            dest="tool_yaml",
            help="Install tool represented by yaml string",)
        command_parser.add_argument(
            "--name",
            help="The name of the tool to install (only applicable "
                 "if the tools file is not provided).")
        command_parser.add_argument(
            "--owner",
            help="The owner of the tool to install (only applicable "
                 "if the tools file is not provided).")
        command_parser.add_argument(
            "--revisions",
            default=None,
            nargs='*',
            dest="revisions",
            help="The revisions of the tool repository that will be installed. "
                 "All revisions must be specified after this flag by a space."
                 "Example: --revisions 0a5c7992b1ac f048033da666"
                 "(Only applicable if the tools file is not provided).")
        command_parser.add_argument(
            "--toolshed",
            dest="tool_shed_url",
            help="The Tool Shed URL where to install the tool from. "
                 "This is applicable only if the tool info is "
                 "provided as an option vs. in the tools file.")

    install_command_parser.add_argument(
        "--section",
        dest="tool_panel_section_id",
        help="Galaxy tool panel section ID where the tool will "
             "be installed (the section must exist in Galaxy; "
             "only applicable if the tools file is not provided).")
    install_command_parser.add_argument(
        "--section_label",
        default=None,
        dest="tool_panel_section_label",
        help="Galaxy tool panel section label where tool will be installed "
             "(if the section does not exist, it will be created; "
             "only applicable if the tools file is not provided).")
    install_command_parser.add_argument(
        "--skip_install_tool_dependencies",
        action="store_true",
        dest="skip_tool_dependencies",
        help="Skip the installation of tool dependencies using classic toolshed packages. "
             "Can be overwritten on a per-tool basis in the tools file.")
    install_command_parser.add_argument(
        "--install_resolver_dependencies",
        action="store_true",
        dest=""
             "",
        help="Install tool dependencies through resolver (e.g. conda). "
             "Will be ignored on galaxy releases older than 16.07. "
             "Can be overwritten on a per-tool basis in the tools file")
    install_command_parser.add_argument(
        "--latest",
        action="store_true",
        dest="force_latest_revision",
        help="Will override the revisions in the tools file and always install the latest revision.")

    for command_parser in [update_command_parser, install_command_parser]:
        command_parser.add_argument(
            "--test",
            action="store_true",
            dest="test",
            help="Run tool tests on install tools, requires Galaxy 18.05 or newer."
        )
        command_parser.add_argument(
            "--test_existing",
            action="store_true",
            help="If testing tools during install, also run tool tests on repositories already installed "
                 "(i.e. skipped repositories)."
        )
        command_parser.add_argument(
            "--test_json",
            dest="test_json",
            help="If testing tools, record tool test output to specified file. "
                 "This file can be turned into reports with ``planemo test_reports <output.json>``."
        )
        command_parser.add_argument(
            "--test_user_api_key",
            dest="test_json",
            help="If testing tools, a user is needed to execute the tests. "
                 "This can be different the --api_key which is assumed to be an admin key. "
                 "If --api_key is a valid user (e.g. it is not a master API key) this does "
                 "not need to be specified and --api_key will be reused."
        )
        command_parser.add_argument(
            "--test_user",
            dest="test_json",
            help="If testing tools, a user is needed to execute the tests. "
                 "If --api_key is a master api key (i.e. not tied to a real user) and "
                 "--test_user_api_key isn't specified, this user email will be used. This "
                 "user will be created if needed."
        )

    # Same test_json as above but language modified for test instead of install/update.
    test_command_parser.add_argument(
        "--test_json",
        dest="test_json",
        help="Record tool test output to specified file. "
             "This file can be turned into reports with ``planemo test_reports <output.json>``."
    )

    test_command_parser.add_argument(
        "--test_user_api_key",
        dest="test_user_api_key",
        help="A user is needed to execute the tests. "
             "This can be different the --api_key which is assumed to be an admin key. "
             "If --api_key is a valid user (e.g. it is not a master API key) this does "
             "not need to be specified and --api_key will be reused."
    )
    test_command_parser.add_argument(
        "--test_user",
        dest="test_user",
        help="A user is needed to execute the tests. "
             "If --api_key is a master api key (i.e. not tied to a real user) and "
             "--test_user_api_key isn't specified, this user email will be used. This "
             "user will be created if needed."
    )

    update_command_parser.set_defaults(
        action="update",
        update_tools=True
    )

    test_command_parser.set_defaults(
        action="test",
        update_tools=False
    )

    return parser


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parser = _parser()
    return parser.parse_args()


def _flatten_repo_info(repositories):
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
    def _strip_revisions(dictionary):
        """
        Iterate through the dictionary and copy its keys and values
        excluding the key `revisions`.
        """
        new_dictionary = {}
        for key, value in dictionary.items():
            if key != 'revisions':
                new_dictionary[key] = value
        return new_dictionary

    flattened_list = []
    for repo_info in repositories:
        revisions = repo_info.get('revisions', [])
        if revisions is not None and len(revisions) > 1:
            for revision in revisions:
                stripped_repo_info = _strip_revisions(repo_info)
                stripped_repo_info['changeset_revision'] = revision
                flattened_list.append(stripped_repo_info)
        elif revisions:  # A single revisions was defined so keep it
            stripped_repo_info = _strip_revisions(repo_info)
            stripped_repo_info['changeset_revision'] = revisions[0]
            flattened_list.append(stripped_repo_info)
        else:  # Revision was not defined at all
            flattened_list.append(repo_info)
    return flattened_list


def install_repository_revision(repository, tool_shed_client):
    """
    Adjusts repository dictionary to bioblend signature and installs single repository
    """
    _ensure_log_configured(__name__)
    repository['new_tool_panel_section_label'] = repository.pop('tool_panel_section_label')
    response = tool_shed_client.install_repository_revision(**repository)
    if isinstance(response, dict) and response.get('status', None) == 'ok':
        # This rare case happens if a repository is already installed but
        # was not recognised as such in the above check. In such a
        # case the return value looks like this:
        # {u'status': u'ok', u'message': u'No repositories were
        #  installed, possibly because the selected repository has
        #  already been installed.'}
        log.debug("\tRepository {0} is already installed.".format(repository['name']))
    return response


def wait_for_install(repository, tool_shed_client, timeout=3600):
    """
    If nginx times out, we look into the list of installed repositories
    and try to determine if a tool of the same namer/owner is still installing.
    Returns True if install finished, returns False when timeout is exceeded.
    """
    def install_done(tool, tool_shed_client):
        installed_repo_list = tool_shed_client.get_repositories()
        for installing_repo in installed_repo_list:
            if (tool['name'] == installing_repo['name']) and (installing_repo['owner'] == tool['owner']):
                if installing_repo['status'] not in ['Installed', 'Error']:
                    return False
        return True

    finished = install_done(repository, tool_shed_client)
    while (not finished) and (timeout > 0):
        timeout -= 10
        time.sleep(10)
        finished = install_done(repository, tool_shed_client)
        if finished:
            return True
    if timeout > 0:
        return True
    else:
        return False


def get_install_repository_manager(options):
    """
    Parse the default input file and proceed to install listed tools.
    :type options: OptionParser object
    :param options: command line arguments parsed by OptionParser
    """
    install_tool_dependencies = INSTALL_TOOL_DEPENDENCIES
    install_repository_dependencies = INSTALL_REPOSITORY_DEPENDENCIES
    install_resolver_dependencies = INSTALL_RESOLVER_DEPENDENCIES

    repo_list_file = options.tool_list_file
    gi = get_galaxy_connection(options, file=repo_list_file, log=log)
    if not gi:
        raise Exception('Could not get a galaxy connection')

    if repo_list_file:
        repository_list = load_yaml_file(repo_list_file)  # Input file contents
        repositories = repository_list['tools']  # The list of tools to install
        install_repository_dependencies = repository_list.get(
            'install_repository_dependencies', INSTALL_REPOSITORY_DEPENDENCIES)
        install_resolver_dependencies = repository_list.get(
            'install_resolver_dependencies', INSTALL_RESOLVER_DEPENDENCIES)
        install_tool_dependencies = repository_list.get(
            'install_tool_dependencies', INSTALL_TOOL_DEPENDENCIES)
    elif options.tool_yaml:
        repositories = [yaml.safe_load(options.tool_yaml)]
    elif options.action == "update":
        get_repository_list = GiToToolYaml(
            gi=gi,
            skip_tool_panel_section_name=False,
            get_data_managers=True
        )
        repository_list = get_repository_list.tool_list
        repositories = repository_list['tools']
    else:
        # An individual tool was specified on the command line
        repositories = [{
            "owner": options.owner,
            "name": options.name,
            "tool_panel_section_id": options.tool_panel_section_id,
            "tool_panel_section_label": options.tool_panel_section_label,
            "tool_shed_url": options.tool_shed_url or MTS,
            "revisions": options.revisions
        }]

    if options.skip_tool_dependencies:
        install_tool_dependencies = False
        install_repository_dependencies = False

    elif repo_list_file:
        install_tool_dependencies = install_tool_dependencies
        install_repository_dependencies = install_repository_dependencies

    install_resolver_dependencies = options.install_resolver_dependencies or install_resolver_dependencies

    force_latest_revision = options.force_latest_revision or options.action == "update"

    return InstallToolManager(repositories=repositories,
                              gi=gi,
                              default_install_tool_dependencies=install_tool_dependencies,
                              default_install_repository_dependencies=install_repository_dependencies,
                              default_install_resolver_dependencies=install_resolver_dependencies,
                              force_latest_revision=force_latest_revision,
                              test=options.test,
                              test_user=options.test_user,
                              test_user_api_key=options.test_user_api_key,
                              test_existing=options.test_existing,
                              test_json=options.test_json,
                              )


class InstallToolManager(object):

    def __init__(self,
                 repositories,
                 gi,
                 default_install_tool_dependencies=INSTALL_TOOL_DEPENDENCIES,
                 default_install_resolver_dependencies=INSTALL_RESOLVER_DEPENDENCIES,
                 default_install_repository_dependencies=INSTALL_REPOSITORY_DEPENDENCIES,
                 require_tool_panel_info=True,
                 force_latest_revision=False,
                 test=False,
                 test_user_api_key=None,
                 test_user="ephemeris@galaxyproject.org",
                 test_existing=False,
                 test_json="tool_test_output.json"):
        self.repositories = repositories
        self.gi = gi
        self.tsc = ToolShedClient(self.gi)
        self.require_tool_panel_info = require_tool_panel_info
        self.install_tool_dependencies = default_install_tool_dependencies
        self.install_resolver_dependencies = default_install_resolver_dependencies
        self.install_repository_dependencies = default_install_repository_dependencies
        self.force_latest_revision = force_latest_revision
        self.errored_repositories = []
        self.skipped_repositories = []
        self.installed_repositories = []
        self.test = test
        self.test_existing = test_existing
        self.test_json = test_json
        self.test_user_api_key = test_user_api_key
        self.test_user = test_user
        self.tests_passed = []
        self.test_exceptions = []

    def install_repositories(self):
        """Attempt to ensure each repository in ``self.repositories`` is installed.
        """
        installation_start = dt.datetime.now()
        installed_repositories_list = installed_repository_revisions(self.gi)  # installed tools list
        counter = 0
        repositories = _flatten_repo_info(self.repositories)
        total_num_repositories = len(repositories)
        default_err_msg = ('All repositories that you are attempting to install '
                           'have been previously installed.')

        # Process each tool/revision: check if it's already installed or install it
        for repository_info in repositories:
            counter += 1
            already_installed = False  # Reset the flag
            repository = self.create_repository_install_payload(repository_info)
            if not repository:
                continue
            repository = self.get_changeset_revision(repository)
            if not repository:
                continue
            # Check if the repository@revision is already installed
            for installed in installed_repositories_list:
                if the_same_repository(installed, repository) and \
                        repository['changeset_revision'] in installed['revisions']:
                    log.debug(
                        "({0}/{1}) repository {2} already installed at revision {3}. Skipping."
                        .format(
                            counter,
                            total_num_repositories,
                            repository['name'],
                            repository['changeset_revision']
                        )
                    )
                    self.skipped_repositories.append({
                        'name': repository['name'],
                        'owner': repository['owner'],
                        'changeset_revision': repository['changeset_revision']
                    })
                    already_installed = True
                    break
            if not already_installed:
                    # Initiate repository installation
                start = dt.datetime.now()
                log.debug(
                    '(%s/%s) Installing repository %s from %s to section "%s" at revision %s (TRT: %s)' % (
                        counter, total_num_repositories,
                        repository['name'],
                        repository['owner'],
                        repository['tool_panel_section_id'] or repository['tool_panel_section_label'],
                        repository['changeset_revision'],
                        dt.datetime.now() - installation_start
                    )
                )
                try:
                    install_repository_revision(repository, self.tsc)
                    log_repository_install_success(
                        repository=repository,
                        start=start,
                        installed_repositories=self.installed_repositories)
                except ConnectionError as e:
                    if default_err_msg in e.body:
                        log.debug("\tRepository %s already installed (at revision %s)" %
                                  (repository['name'], repository['changeset_revision']))
                    else:
                        if "504" in e.message:
                            log.debug("Timeout during install of %s, extending wait to 1h", repository['name'])
                            success = wait_for_install(repository=repository, tool_shed_client=self.tsc, timeout=3600)
                            if success:
                                log_repository_install_success(
                                    repository=repository,
                                    start=start,
                                    installed_repositories=self.installed_repositories)
                            else:
                                log_repository_install_error(
                                    repository=repository,
                                    start=start, msg=e.body,
                                    errored_repositories=self.errored_repositories)
                        else:
                            log_repository_install_error(
                                repository=repository,
                                start=start,
                                msg=e.body,
                                errored_repositories=self.errored_repositories)
        log.info("Installed repositories ({0}): {1}".format(
            len(self.installed_repositories),
            [(
                t['name'],
                t.get('changeset_revision')
            ) for t in self.installed_repositories])
        )
        log.info("Skipped repositories ({0}): {1}".format(
            len(self.skipped_repositories),
            [(
                t['name'],
                t.get('changeset_revision')
            ) for t in self.skipped_repositories])
        )
        log.info("Errored repositories ({0}): {1}".format(
            len(self.errored_repositories),
            [(
                t['name'],
                t.get('changeset_revision', "")
            ) for t in self.errored_repositories])
        )
        log.info("All repositories have been installed.")
        if self.test:
            target_repositories = self.installed_repositories
            if self.test_existing:
                target_repositories += self.skipped_repositories
            self.test_repositories(target_repositories=target_repositories)
        log.info("Total run time: {0}".format(dt.datetime.now() - installation_start))

    def test_repositories(self, target_repositories=None):
        """Run tool tests for each tool in supplied repositories list or ``self.repositories``.
        """
        tool_test_start = dt.datetime.now()
        if target_repositories is None:
            # Consider a variant of this that doesn't even consume a tool list YAML? target
            # something like installed_repository_revisions(self.gi)
            target_repositories = self.repositories
        installed_tools = []
        for target_repository in target_repositories:
            repo_tools = tools_for_repository(self.gi, target_repository)
            installed_tools.extend(repo_tools)

        all_test_results = []

        for tool in installed_tools:
            tool_test_results = self._test_tool(tool)
            all_test_results.extend(tool_test_results)

        report_obj = {
            'version': '0.1',
            'tests': all_test_results,
        }
        with open(self.test_json or "tool_test_output.json", "w") as f:
            json.dump(report_obj, f)
        log.info("Passed tool tests ({0}): {1}".format(
            len(self.tests_passed),
            [t for t in self.tests_passed])
        )
        log.info("Failed tool tests ({0}): {1}".format(
            len(self.test_exceptions),
            [t[0] for t in self.test_exceptions])
        )
        log.info("Total tool test time: {0}".format(dt.datetime.now() - tool_test_start))

    def _test_tool(self, tool):
        test_user_api_key = self.test_user_api_key
        if test_user_api_key is None:
            whoami = self.gi.make_get_request(self.gi.url + "/whoami").json()
            if whoami is not None:
                test_user_api_key = self.gi.key
        galaxy_interactor_kwds = {
            "galaxy_url": re.sub('/api', '', self.gi.url),
            "master_api_key": self.gi.key,
            "api_key": None,  # TODO
            "keep_outputs_dir": '',
        }
        if test_user_api_key is None:
            galaxy_interactor_kwds["test_user"] = self.test_user
        galaxy_interactor = GalaxyInteractorApi(**galaxy_interactor_kwds)
        tool_id = tool["id"]
        tool_version = tool["version"]
        tool_test_dicts = galaxy_interactor.get_tool_tests(tool_id, tool_version=tool_version)
        test_indices = list(range(len(tool_test_dicts)))
        tool_test_results = []

        for test_index in test_indices:
            test_id = tool_id + "-" + str(test_index)

            def register(job_data):
                tool_test_results.append({
                    'id': test_id,
                    'has_data': True,
                    'data': job_data,
                })

            try:
                verify_tool(
                    tool_id, galaxy_interactor, test_index=test_index, tool_version=tool_version,
                    register_job_data=register, quiet=True
                )
                self.tests_passed.append(test_id)
            except Exception as e:
                self.test_exceptions.append((test_id, e))

        return tool_test_results

    def create_repository_install_payload(self, repository_info):
        """
        For each listed repository (repository_info) we generate a payload that contains all
        required parameters, filling up missing parameters with user-defined and/or default settings.
        Return `None` if a required parameter is missing
        """
        repository = dict()  # Payload for the repository we are installing
        # Copy required `repository_info` keys into the `repository` dict
        repository['name'] = repository_info.get('name', None)
        repository['owner'] = repository_info.get('owner', None)
        repository['tool_panel_section_id'] = repository_info.get('tool_panel_section_id', None)
        repository['tool_panel_section_label'] = repository_info.get('tool_panel_section_label', None)
        # Check if all required repository sections have been provided; if not, skip
        # the installation of this repository. Note that data managers are an exception
        # but they must contain string `data_manager` within the repository name.
        now = dt.datetime.now()
        missing_required = not repository['name'] or not repository['owner']
        if not missing_required and self.require_tool_panel_info:
            if not (repository['tool_panel_section_id'] or repository['tool_panel_section_label']) and \
                    'data_manager' not in repository.get('name', ''):
                log_repository_install_error(
                    repository,
                    start=now,
                    msg='tool panel section or tool panel name required',
                    errored_repositories=self.errored_repositories)
                return None
        if not repository['name'] or not repository['owner']:
            log_repository_install_error(
                repository,
                start=now,
                msg="Missing required field",
                errored_repositories=self.errored_repositories)
            return None
        # Populate fields that can optionally be provided (if not provided, set
        # defaults).
        repository['install_tool_dependencies'] = \
            repository_info.get('install_tool_dependencies', self.install_tool_dependencies)
        repository['install_repository_dependencies'] = \
            repository_info.get('install_repository_dependencies', self.install_repository_dependencies)
        repository['install_resolver_dependencies'] = \
            repository_info.get('install_resolver_dependencies', self.install_resolver_dependencies)
        tool_shed = repository_info.get('tool_shed_url', MTS)
        if not tool_shed.endswith('/'):
            tool_shed += '/'
        if not tool_shed.startswith('http'):
            tool_shed = 'https://' + tool_shed
        repository['tool_shed_url'] = tool_shed
        repository['changeset_revision'] = repository_info.get('changeset_revision', None)
        return repository

    def get_changeset_revision(self, repository):
        """
        Select the correct changeset revision for a repository,
        and make sure the repository exists (i.e a request to the tool shed with name and owner returns a list of revisions).
        Return repository or None, if the repository could not be found on the specified tool shed.
        """
        ts = ToolShedInstance(url=repository['tool_shed_url'])
        # Get the set revision or set it to the latest installable revision
        installable_revisions = ts.repositories.get_ordered_installable_revisions(repository['name'], repository['owner'])
        if not installable_revisions:  # Repo does not exist in tool shed
            now = dt.datetime.now()
            log_repository_install_error(
                repository,
                start=now,
                msg="Repository does not exist in tool shed",
                errored_repositories=self.errored_repositories)
            return None
        if not repository['changeset_revision'] or self.force_latest_revision:
            repository['changeset_revision'] = installable_revisions[-1]
        return repository


def main():
    global log
    disable_external_library_logging()
    options = _parse_cli_options()
    log = setup_global_logger(name=__name__, log_file=options.log_file)
    install_tool_manager = None
    if options.tool_list_file or options.tool_yaml or \
            options.name and options.owner and (options.tool_panel_section_id or options.tool_panel_section_label):
        if options.action == "update":
            sys.exit("update command can not be used together with tools to be installed.")
        install_tool_manager = get_install_repository_manager(options)
        if options.action == "test":
            install_tool_manager.test_repositories()
        else:
            install_tool_manager.install_repositories()
    elif options.update_tools:
        install_tool_manager = get_install_repository_manager(options)
        install_tool_manager.install_repositories()
    else:
        sys.exit("Must provide a tool list file, individual tools info , a list of data manager tasks or issue the update command. "
                 "Look at usage.")

    if install_tool_manager.errored_repositories:
        sys.exit(EXIT_CODE_INSTALL_ERRORS)
    elif install_tool_manager.test_exceptions:
        sys.exit(EXIT_CODE_TOOL_TEST_ERRORS)


if __name__ == "__main__":
    main()
