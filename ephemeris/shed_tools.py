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

class InstallToolManager(object):
    """Manages the installation of new tools on a galaxy instance"""

    def __init__(self, galaxy_instance, log):
        """Initialize a new tool manager"""
        self.gi = galaxy_instance
        self.log = log

    @property
    def installed_tools(self):
        """Get currently installed tools"""
        return GiToToolYaml(
            gi=self.gi,
            skip_tool_panel_section_name=False,
            get_data_managers=True
        ).tool_list.get("tools")


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

    def install_repository_revision(self, repository, tool_shed_client):
        """
        Adjusts repository dictionary to bioblend signature and installs single repository
        """
        repository['new_tool_panel_section_label'] = repository.pop('tool_panel_section_label')
        response = tool_shed_client.install_repository_revision(**repository)
        if isinstance(response, dict) and response.get('status', None) == 'ok':
            # This rare case happens if a repository is already installed but
            # was not recognised as such in the above check. In such a
            # case the return value looks like this:
            # {u'status': u'ok', u'message': u'No repositories were
            #  installed, possibly because the selected repository has
            #  already been installed.'}
            self.log.debug("\tRepository {0} is already installed.".format(repository['name']))
        return response

    def install_tools(self, tools):
        """Install a list of tools on the current galaxy"""
        installation_start = dt.datetime.now()
        counter = 0
        total_num_repositories = len(tools)
        flattened_tool_list = []  # TODO: Implement/copy method to flatten tool list for revisions

        #TODO: Implement code to filter the tool list for already installed tools
        #TODO: Implement code in get_tool_list to get the repository list without the squashed revisions
        #TODO: Prevent code duplication all methods concerning tool lists should be in the get-tool-ist file

        for tool in flattened_tool_list:
            counter += 1
            start = dt.datetime.now()
            self.log.debug(
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


def get_tool_list_from_args(args):
    """Helper method to get a tool list """
    # PLACEHOLDER
    tools = []
    return tools


def main():
    disable_external_library_logging()
    args = parser().parse_args()
    log = setup_global_logger(name=__name__, log_file=args.log_file)
    gi = get_galaxy_connection(args, file=args.tool_list_file, log=log, login_required=True)
    install_tool_manager = InstallToolManager(gi, log=log)
    tools = get_tool_list_from_args(args)
    if args.action == "update":
        install_tool_manager.update_tools(tools)
    elif args.action == "test":
        install_tool_manager.install_tools(tools)
    elif args.action == "install":
        install_tool_manager.test_tools(tools)
    else:
        raise Exception("This point in the code should not be reached. Please contact the developers.")


if __name__ == "__main__":
    main()
