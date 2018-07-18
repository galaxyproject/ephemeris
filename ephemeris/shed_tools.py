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

class InstallToolManager(object):
    """Manages the installation of new tools on a galaxy instance"""
    def __init__(self,galaxy_instance):
        """Initialize a new tool manager"""
        self.gi = galaxy_instance

    @property
    def installed_tools(self):
        """Get currently installed tools"""
        return GiToToolYaml(
            gi=self.gi,
            skip_tool_panel_section_name=False,
            get_data_managers=True
        ).tool_list.get("tools")

    def install_tools(self,tools, log):
        """Install a list of tools on the current galaxy"""
        # Insert code here to install tools

    def update_tools(self,log, tools=None):
        if tools is None:
            to_be_updated_tools=self.installed_tools
        else:
            to_be_updated_tools= tools
        # Insert code here to update tools

    def test_tools(self, log, tools=None):
        if tools is None:
            to_be_tested_tools=self.installed_tools
        else:
            to_be_tested_tools= tools
        # Insert code here to test the tools


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
