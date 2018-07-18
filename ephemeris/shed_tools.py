"""
A tool to automate installation of tool repositories from a Galaxy Tool Shed
into an instance of Galaxy.

Shed-tools has three commands: update, test and install.

Update simply updates all the tools in a Galaxy given connection details on the command line.

Test: ##PLACEHOLDER##

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
from ephemeris_log import setup_global_logger, disable_external_library_logging
from .get_tool_list_from_galaxy import GiToToolYaml, tools_for_repository
from .shed_tools_args import parser
from . import get_galaxy_connection
import datetime as dt
from bioblend.galaxy.toolshed import ToolShedClient
from bioblend.toolshed import ToolShedInstance

class InstallToolManager(object):
    """Manages the installation of new tools on a galaxy instance"""

    def __init__(self,
                 galaxy_instance):
        """Initialize a new tool manager"""
        self.gi = galaxy_instance
        self.tool_shed_client = ToolShedClient(self.gi)

    @property
    def installed_tools(self):
        """Get currently installed tools"""
        return GiToToolYaml(
            gi=self.gi,
            skip_tool_panel_section_name=False,
            get_data_managers=True,
            flatten_revisions=False # We want all the revisions to be there
        ).tool_list.get("tools")


    @property
    def installed_repos(self):
        _flatten_repo_info(self.installed_tools)


    def filter_installed_repos(self, repos):
        """This filters a list of tools"""
        not_installed_repos = []
        already_installed_repos = []
        for repo in iter(repos):
            for installed_tool in iter(self.installed_tools):
                if the_same_repository(installed_tool, repo):
                    already_installed_repos.append(repo)
                else:
                    not_installed_repos.append(repo)
        return not_installed_repos, already_installed_repos


    def install_tools(self,
                      tools,
                      log = None,
                      force_latest_revision=False,
                      default_toolshed='https://toolshed.g2.bx.psu.edu/',
                      default_install_tool_dependencies=False,
                      default_install_resolver_dependencies=True,
                      default_install_repository_dependencies=True):
        """Install a list of tools on the current galaxy"""
        installation_start = dt.datetime.now()
        counter = 0
        total_num_repositories = len(tools)
        flattened_tool_list = _flatten_repo_info(tools)

        not_installed_tools, already_installed_tools = self.filter_installed_tools(flattened_tool_list)


        for tool in not_installed_tools:
            counter += 1
            start = dt.datetime.now()
            if log:
                log.debug(
                '(%s/%s) Installing repository %s from %s to section "%s" at revision %s (TRT: %s)' % (
                    counter, total_num_repositories,
                    tool['name'],
                    tool['owner'],
                    tool['tool_panel_section_id'] or tool['tool_panel_section_label'] or "",
                    tool['changeset_revision'],
                    dt.datetime.now() - installation_start
                    )
                )

    def update_tools(self, tools=None):
        if tools is None:
            to_be_updated_tools = self.installed_tools
        else:
            to_be_updated_tools = tools
        # Insert code here to update tools

    def test_tools(self, tools=None):
        if tools is None:
            to_be_tested_tools = self.installed_tools
        else:
            to_be_tested_tools = tools
        # Insert code here to test the tools

    def install_repository_revision(self, repository, log=None):
        """
        Adjusts repository dictionary to bioblend signature and installs single repository
        """
        repository['new_tool_panel_section_label'] = repository.pop('tool_panel_section_label')
        response = self.tool_shed_client.install_repository_revision(**repository)
        if isinstance(response, dict) and response.get('status', None) == 'ok':
            # This rare case happens if a repository is already installed but
            # was not recognised as such in the above check. In such a
            # case the return value looks like this:
            # {u'status': u'ok', u'message': u'No repositories were
            #  installed, possibly because the selected repository has
            #  already been installed.'}
            if log:
                log.debug("\tRepository {0} is already installed.".format(repository['name']))
        return response


def format_tool_shed_url(tool_shed_url):
    formatted_tool_shed_url = tool_shed_url
    if not formatted_tool_shed_url.endswith('/'):
        formatted_tool_shed_url += '/'
    if not formatted_tool_shed_url.startswith('http'):
        formatted_tool_shed_url = 'https://' + formatted_tool_shed_url
    return formatted_tool_shed_url

def the_same_repository(repo_1_info, repo_2_info):
    """
    Given two dicts containing info about tools, determine if they are the same
    tool.
    Each of the dicts must have the following keys: `name`, `owner`, and
    (either `tool_shed` or `tool_shed_url`).
    """
    # Sort from most unique to least unique for fast comparison.
    if repo_1_info.get('changeset_revision') == repo_2_info.get('changeset_revision'):
        if repo_1_info.get('name') == repo_2_info.get('name'):
            if repo_1_info.get('owner') == repo_2_info.get('owner'):
                t1ts = repo_1_info.get('tool_shed', repo_1_info.get('tool_shed_url', None))
                t2ts = repo_2_info.get('tool_shed', repo_2_info.get('tool_shed_url', None))
                if (t1ts in t2ts or t2ts in t1ts):
                    return True
    return False

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
    flattened_list = []
    for repo_info in iter(repositories):
        if 'revisions' in repo_info:
            revisions = repo_info.get('revisions', [])
            repo_info.pop('revisions', None) # Set default to avoid key error
            for revision in revisions:
                repo_info['changeset_revision'] = revision
                flattened_list.append(repo_info)
        else:  # Revision was not defined at all
            flattened_list.append(repo_info)
    return flattened_list

def get_tool_list_from_args(args):
    """Helper method to get a tool list """
    # PLACEHOLDER
    tools = []
    return tools

def log_repository_install_error(self, repository, start, msg, errored_repositories):
    """
    Log failed tool installations
    """
    end = dt.datetime.now()
    self.log.error(
        "\t* Error installing a repository (after %s seconds)! Name: %s," "owner: %s, ""revision: %s, error: %s",
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

def log_repository_install_success(self, repository, start, installed_repositories):
    """
    Log successful repository installation.
    Tools that finish in error still count as successful installs currently.
    """
    end = dt.datetime.now()
    installed_repositories.append({
        'name': repository['name'],
        'owner': repository['owner'],
        'revision': repository['changeset_revision']})
    self.log.debug(
        "\trepository %s installed successfully (in %s) at revision %s" % (
            repository['name'],
            str(end - start),
            repository['changeset_revision']
        )
    )



def main():
    disable_external_library_logging()
    args = parser().parse_args()
    log = setup_global_logger(name=__name__, log_file=args.log_file)
    gi = get_galaxy_connection(args, file=args.tool_list_file, log=log, login_required=True)
    install_tool_manager = InstallToolManager(gi)
    tools = get_tool_list_from_args(args)
    if args.action == "update":
        install_tool_manager.update_tools(tools)
    elif args.action == "test":
        install_tool_manager.install_tools(tools)
    elif args.action == "install":
        install_tool_manager.test_tools(tools,log=log)
    else:
        raise Exception("This point in the code should not be reached. Please contact the developers.")


if __name__ == "__main__":
    main()
