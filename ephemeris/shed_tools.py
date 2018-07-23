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
import datetime as dt
import json
import re
import time
from collections import namedtuple

import yaml
from bioblend.galaxy.client import ConnectionError
from bioblend.galaxy.toolshed import ToolShedClient
from galaxy.tools.verify.interactor import GalaxyInteractorApi, verify_tool

from . import get_galaxy_connection, load_yaml_file
from .ephemeris_log import disable_external_library_logging, setup_global_logger
from .get_tool_list_from_galaxy import GiToToolYaml, the_same_repository, tools_for_repository
from .shed_tools_args import parser
from .shed_tools_methods import complete_repo_information, flatten_repo_info


class InstallToolManager(object):
    """Manages the installation of new tools on a galaxy instance"""

    def __init__(self,
                 galaxy_instance):
        """Initialize a new tool manager"""
        self.gi = galaxy_instance
        self.tool_shed_client = ToolShedClient(self.gi)

    def installed_tools(self):
        """Get currently installed tools"""
        return GiToToolYaml(
            gi=self.gi,
            skip_tool_panel_section_name=False,
            get_data_managers=True,
            get_all_tools=True
        ).tool_list.get("tools")

    def filter_installed_repos(self, repos, check_revision=True):
        # TODO: Find a speedier algorithm.
        """This filters a list of tools"""
        not_installed_repos = []
        already_installed_repos = []
        if check_revision:
            # If we want to check if revisions are equal, flatten the list,
            # so each tool - revision combination has its own entry
            installed_repos = flatten_repo_info(self.installed_tools())
        else:
            # If we do not care about revision equality, do not do the flatten
            # action to limit the number of comparisons.
            installed_repos = self.installed_tools()

        for repo in repos:
            for installed_repo in installed_repos:
                if the_same_repository(installed_repo, repo, check_revision):
                    already_installed_repos.append(repo)
                    break
            else:  # This executes when the for loop completes and no match has been found.
                not_installed_repos.append(repo)
        FilterResults = namedtuple("FilterResults", ["not_installed_repos", "already_installed_repos"])
        return FilterResults(already_installed_repos=already_installed_repos, not_installed_repos=not_installed_repos)

    def install_tools(self,
                      tools,
                      log=None,
                      force_latest_revision=False,
                      default_toolshed='https://toolshed.g2.bx.psu.edu/',
                      default_install_tool_dependencies=False,
                      default_install_resolver_dependencies=True,
                      default_install_repository_dependencies=True):
        """Install a list of tools on the current galaxy"""
        if not tools:
            raise ValueError("Empty list of tools was given")
        installation_start = dt.datetime.now()
        installed_repositories = []
        skipped_repositories = []
        errored_repositories = []
        counter = 0

        # Start by flattening the repo list per revision
        flattened_repos = flatten_repo_info(tools)
        total_num_repositories = len(flattened_repos)

        # Complete the repo information, and make sure each tool has a revision
        repository_list = []
        for repository in flattened_repos:
            start = dt.datetime.now()
            try:
                complete_repo = complete_repo_information(
                    repository,
                    default_toolshed_url=default_toolshed,
                    require_tool_panel_info=True,
                    default_install_tool_dependencies=default_install_tool_dependencies,
                    default_install_resolver_dependencies=default_install_resolver_dependencies,
                    default_install_repository_dependencies=default_install_repository_dependencies,
                    force_latest_revision=force_latest_revision)
                repository_list.append(complete_repo)
            except (LookupError, KeyError) as e:
                if log:
                    log_repository_install_error(repository, start, e.message, log)
                errored_repositories.append(repository)

        # Filter out already installed repos
        not_installed_repos, already_installed_repos = self.filter_installed_repos(repository_list)

        for skipped_repo in already_installed_repos:
            counter += 1
            if log:
                log_repository_install_skip(skipped_repo, counter, total_num_repositories, log)
            skipped_repositories.append(skipped_repo)

        # Install repos
        for repository in not_installed_repos:
            counter += 1
            log_repository_install_start(repository, counter=counter, installation_start=installation_start, log=log,
                                         total_num_repositories=total_num_repositories)
            result = self.install_repository_revision(repository, log)
            if result == "error":
                errored_repositories.append(repository)
            elif result == "skipped":
                skipped_repositories.append(repository)
            elif result == "installed":
                installed_repositories.append(repository)

        # Log results
        if log:
            log.info("Installed repositories ({0}): {1}".format(
                len(installed_repositories),
                [(
                    t['name'],
                    t.get('changeset_revision')
                ) for t in installed_repositories])
            )
            log.info("Skipped repositories ({0}): {1}".format(
                len(skipped_repositories),
                [(
                    t['name'],
                    t.get('changeset_revision')
                ) for t in skipped_repositories])
            )
            log.info("Errored repositories ({0}): {1}".format(
                len(errored_repositories),
                [(
                    t['name'],
                    t.get('changeset_revision', "")
                ) for t in errored_repositories])
            )
            log.info("All repositories have been installed.")
            log.info("Total run time: {0}".format(dt.datetime.now() - installation_start))
        InstallResults = namedtuple("InstallResults",
                                    ["installed_repositories", "errored_repositories", "skipped_repositories"])
        return InstallResults(installed_repositories=installed_repositories,
                              skipped_repositories=skipped_repositories,
                              errored_repositories=errored_repositories)

    def update_tools(self, tools=None, log=None, **kwargs):
        if not tools:  # Tools None or empty list
            tools = self.installed_tools()
        else:
            not_installed_tools, already_installed_tools = self.filter_installed_repos(tools, check_revision=False)
            if not_installed_tools:
                if log:
                    log.warning("The following tools are not installed and will not be upgraded: {0}".format(
                        not_installed_tools))
            tools = already_installed_tools
        return self.install_tools(tools, force_latest_revision=True, log=log, **kwargs)

    def test_tools(self,
                   test_json,
                   tools=None,
                   log=None,
                   test_user_api_key=None,
                   test_user="ephemeris@galaxyproject.org"
                   ):
        """Run tool tests for each tool in supplied tool list list or ``self.installed_tools()``.
        """
        tool_test_start = dt.datetime.now()
        tests_passed = []
        test_exceptions = []

        if not tools:  # If tools is None or empty list
            # Consider a variant of this that doesn't even consume a tool list YAML? target
            # something like installed_repository_revisions(self.gi)
            tools = self.installed_tools()

        target_repositories = flatten_repo_info(tools)

        installed_tools = []
        for target_repository in target_repositories:
            repo_tools = tools_for_repository(self.gi, target_repository)
            installed_tools.extend(repo_tools)

        all_test_results = []

        for tool in installed_tools:
            results = self._test_tool(tool, test_user, test_user_api_key)
            all_test_results.extend(results.tool_test_results)
            tests_passed.extend(results.tests_passed)
            test_exceptions.extend(results.test_extensions)

        report_obj = {
            'version': '0.1',
            'tests': all_test_results,
        }
        with open(test_json, "w") as f:
            json.dump(report_obj, f)
        if log:
            log.info("Passed tool tests ({0}): {1}".format(
                len(tests_passed),
                [t for t in tests_passed])
            )
            log.info("Failed tool tests ({0}): {1}".format(
                len(test_exceptions),
                [t[0] for t in test_exceptions])
            )
            log.info("Total tool test time: {0}".format(dt.datetime.now() - tool_test_start))

    def _test_tool(self, tool, test_user, test_user_api_key):

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
            galaxy_interactor_kwds["test_user"] = test_user
        galaxy_interactor = GalaxyInteractorApi(**galaxy_interactor_kwds)
        tool_id = tool["id"]
        tool_version = tool["version"]
        tool_test_dicts = galaxy_interactor.get_tool_tests(tool_id, tool_version=tool_version)
        test_indices = list(range(len(tool_test_dicts)))
        tool_test_results = []
        tests_passed = []
        test_exceptions = []

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
                tests_passed.append(test_id)
            except Exception as e:
                test_exceptions.append((test_id, e))
        Results = namedtuple("Results", ["tool_test_results", "tests_passed", "test_exceptions"])
        return Results(tool_test_results=tool_test_results,
                       tests_passed=tests_passed,
                       test_exceptions=test_exceptions)

    def install_repository_revision(self, repository, log):
        default_err_msg = ('All repositories that you are attempting to install '
                           'have been previously installed.')
        start = dt.datetime.now()
        try:
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
            if log:
                log_repository_install_success(
                    repository=repository,
                    start=start,
                    log=log)
            return "installed"
        except ConnectionError as e:
            if default_err_msg in e.body:
                # THIS SHOULD NOT HAPPEN DUE TO THE CHECKS EARLIER
                if log:
                    log.debug("\tRepository %s already installed (at revision %s)" %
                              (repository['name'], repository['changeset_revision']))
                return "skipped"
            elif "504" in e.message:
                if log:
                    log.debug("Timeout during install of %s, extending wait to 1h", repository['name'])
                success = self.wait_for_install(repository=repository, log=log, timeout=3600)
                if success:
                    if log:
                        log_repository_install_success(
                            repository=repository,
                            start=start,
                            log=log)
                    return "installed"
                else:
                    if log:
                        log_repository_install_error(
                            repository=repository,
                            start=start, msg=e.body,
                            log=log)
                    return "error"
            else:
                if log:
                    log_repository_install_error(
                        repository=repository,
                        start=start, msg=e.body,
                        log=log)
                return "error"

    def wait_for_install(self, repository, log=None, timeout=3600):
        """
        If nginx times out, we look into the list of installed repositories
        and try to determine if a tool of the same namer/owner is still installing.
        Returns True if install finished successfully,
        returns False when timeout is exceeded or installation has failed.
        """
        start = dt.datetime.now()
        while (dt.datetime.now() - start) < dt.timedelta(seconds=timeout):
            try:
                installed_repo_list = self.tool_shed_client.get_repositories()
                for installing_repo in installed_repo_list:
                    if (repository['name'] == installing_repo['name']) and (
                                installing_repo['owner'] == repository['owner']):
                        if installing_repo['status'] == 'Installed':
                            return True
                        elif installing_repo['status'] == 'Error':
                            return False
                        else:
                            time.sleep(10)
            except ConnectionError as e:
                if log:
                    log.warning('Failed to get repositories list: %s', str(e))
                time.sleep(10)
        return False


def log_repository_install_error(repository, start, msg, log):
    """
    Log failed tool installations. Return a dictionary wiyh information
    """
    end = dt.datetime.now()
    log.error(
        "\t* Error installing a repository (after %s seconds)! Name: %s," "owner: %s, ""revision: %s, error: %s",
        str(end - start),
        repository.get('name', ""),
        repository.get('owner', ""),
        repository.get('changeset_revision', ""),
        msg)


def log_repository_install_success(repository, start, log):
    """
    Log successful repository installation.
    Tools that finish in error still count as successful installs currently.
    """
    end = dt.datetime.now()
    log.debug(
        "\trepository %s installed successfully (in %s) at revision %s" % (
            repository['name'],
            str(end - start),
            repository['changeset_revision']
        )
    )


def log_repository_install_skip(repository, counter, total_num_repositories, log):
    log.debug(
        "({0}/{1}) repository {2} already installed at revision {3}. Skipping."
        .format(
            counter,
            total_num_repositories,
            repository['name'],
            repository['changeset_revision']
        )
    )


def log_repository_install_start(repository, counter, total_num_repositories, installation_start, log):
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


def args_to_tools(args):
    if args.tool_list_file:
        tool_list = load_yaml_file(args.tool_list_file)
        tools = tool_list['tools']
    elif args.tool_yaml:
        tools = [yaml.safe_load(args.tool_yaml)]
    elif args.name and args.owner:
        tool = dict(
            owner=args.owner,
            name=args.name,
            tool_panel_section_id=args.tool_panel_section_id,
            tool_panel_section_label=args.tool_panel_section_label,
            revisions=args.revisions
        )
        if args.tool_shed_url:
            tool["tool_shed_url"] = args.tool_shed_url
        tools = [tool]
    else:
        tools = []
    return tools


def main():
    disable_external_library_logging()
    args = parser().parse_args()
    log = setup_global_logger(name=__name__, log_file=args.log_file)
    gi = get_galaxy_connection(args, file=args.tool_list_file, log=log, login_required=True)
    install_tool_manager = InstallToolManager(gi)

    tools = args_to_tools(args)

    if args.tool_list_file:
        tool_list = load_yaml_file(args.tool_list_file)
    else:
        tool_list = dict()

    # Get some of the other installation arguments
    kwargs = dict(
        default_install_tool_dependencies=tool_list.get(
            "install_tool_dependencies") or args.install_tool_dependencies,
        default_install_repository_dependencies=tool_list.get(
            "install_repository_dependencies") or args.install_repository_dependencies,
        default_install_resolver_dependencies=tool_list.get(
            "install_resolver_dependencies") or args.install_resolver_dependencies,
    )

    # Start installing/updating and store the results in install_results.
    # Or do testing if the action is `test`
    install_results = None
    if args.action == "update":
        install_results = install_tool_manager.update_tools(
            tools=tools,
            log=log,
            **kwargs)
    elif args.action == "install":
        install_results = install_tool_manager.install_tools(
            tools,
            log=log,
            force_latest_revision=args.force_latest_revision,
            **kwargs)
    elif args.action == "test":
        install_tool_manager.test_tools(
            test_json=args.test_json,
            tools=tools,
            log=log,
            test_user_api_key=args.test_user_api_key,
            test_user=args.test_user)
    else:
        raise NotImplementedError("This point in the code should not be reached. Please contact the developers.")

    # Run tests on the install results if required.
    if install_results and args.test or args.test_existing:
        to_be_tested_tools = install_results.installed_repositories
        if args.test_existing:
            to_be_tested_tools.extend(install_results.skipped_repositories)

        install_tool_manager.test_tools(
            test_json=args.test_json,
            tools=to_be_tested_tools,
            log=log,
            test_user_api_key=args.test_user_api_key,
            test_user=args.test_user)


if __name__ == "__main__":
    main()
