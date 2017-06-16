"""
**NOTE:** *While shed-install can be used to run data managers, it is recommended
to use run-data-managers instead.*

A script to automate installation of tool repositories from a Galaxy Tool Shed
into an instance of Galaxy.
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
import logging
import sys
import time

from argparse import ArgumentParser

import yaml

from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.client import ConnectionError
from bioblend.galaxy.toolshed import ToolShedClient
from bioblend.toolshed import ToolShedInstance

from . import get_galaxy_connection

from .common_parser import get_common_args

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


class ProgressConsoleHandler(logging.StreamHandler):
    """
    A handler class which allows the cursor to stay on
    one line for selected messages
    """
    on_same_line = False

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            same_line = hasattr(record, 'same_line')
            if self.on_same_line and not same_line:
                stream.write('\r\n')
            stream.write(msg)
            if same_line:
                stream.write('.')
                self.on_same_line = True
            else:
                stream.write('\r\n')
                self.on_same_line = False
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


def _disable_external_library_logging():
    # Omit (most of the) logging by external libraries
    logging.getLogger('bioblend').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    try:
        logging.captureWarnings(True)  # Capture HTTPS warngings from urllib3
    except AttributeError:
        pass


def _ensure_log_configured():
    # For library-style usage - just ensure a log exists and use ephemeris name.
    if 'log' not in globals():
        global log
        log = setup_global_logger()


def setup_global_logger(include_file=False):
    formatter = logging.Formatter('%(asctime)s %(levelname)-5s - %(message)s')
    progress = ProgressConsoleHandler()
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(progress)

    if include_file:
        file_handler = logging.FileHandler('/tmp/galaxy_tool_install.log')
        logger.addHandler(file_handler)
    return logger


def log_tool_install_error(tool, start, msg, errored_tools):
    """
    Log failed tool installations
    """
    _ensure_log_configured()
    end = dt.datetime.now()
    log.error("\t* Error installing a tool (after %s seconds)! Name: %s," "owner: %s, ""revision: %s, error: %s",
              str(end - start),
              tool.get('name', ""),
              tool.get('owner', ""),
              tool.get('changeset_revision', ""),
              msg)
    errored_tools.append({'name': tool.get('name', ""),
                          'owner': tool.get('owner', ""),
                          'revision': tool.get('changeset_revision', ""),
                          'error': msg})


def log_tool_install_success(tool, start, installed_tools):
    """
    Log successfull tool installation.
    Tools that finish in error still count as successfull installs currently.
    """
    _ensure_log_configured()
    end = dt.datetime.now()
    installed_tools.append({'name': tool['name'], 'owner': tool['owner'],
                           'revision': tool['changeset_revision']})
    log.debug("\tTool %s installed successfully (in %s) at revision %s" %
              (tool['name'], str(end - start), tool['changeset_revision']))


def load_input_file(tool_list_file='tool_list.yaml'):
    """
    Load YAML from the `tool_list_file` and return a dict with the content.
    """
    with open(tool_list_file, 'r') as f:
        tl = yaml.load(f)
    return tl


def dump_to_yaml_file(content, file_name):
    """
    Dump YAML-compatible `content` to `file_name`.
    """
    with open(file_name, 'w') as f:
        yaml.dump(content, f, default_flow_style=False)


def galaxy_instance(url=None, api_key=None):
    """
    Get an instance of the `GalaxyInstance` object. If the arguments are not
    provided, load the default values using `load_input_file` method.
    """
    if not (url and api_key):
        tl = load_input_file()
        url = tl['galaxy_instance']
        api_key = tl['api_key']
    return GalaxyInstance(url, api_key)


def tool_shed_client(gi=None):
    """
    Get an instance of the `ToolShedClient` on a given Galaxy instance. If no
    value is provided for the `galaxy_instance`, use the default provided via
    `load_input_file`.
    """
    if not gi:
        gi = galaxy_instance()
    return ToolShedClient(gi)


def the_same_tool(tool_1_info, tool_2_info):
    """
    Given two dicts containing info about tools, determine if they are the same
    tool.
    Each of the dicts must have the following keys: `name`, `owner`, and
    (either `tool_shed` or `tool_shed_url`).
    """
    t1ts = tool_1_info.get('tool_shed', tool_1_info.get('tool_shed_url', None))
    t2ts = tool_2_info.get('tool_shed', tool_2_info.get('tool_shed_url', None))

    if tool_1_info.get('name') == tool_2_info.get('name') and \
       tool_1_info.get('owner') == tool_2_info.get('owner') and \
       (t1ts in t2ts or t2ts in t1ts):
        return True
    return False


def installed_tool_revisions(gi=None, omit=None):
    """
    Get a list of tool revisions installed from a Tool Shed on a Galaxy instance.
    Included are all the tool revisions that were installed from a Tool
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
                 `installed_tools` function
    """
    if not omit:
        omit = []
    tsc = tool_shed_client(gi)
    installed_revisions_list = []
    itl = tsc.get_repositories()
    for it in itl:
        if it['status'] == 'Installed':
            skip = False
            # Check if we already processed this tool and, if so, add the new
            # revision to the existing list entry
            for ir in installed_revisions_list:
                if the_same_tool(it, ir):
                    ir['revisions'].append(it.get('changeset_revision', None))
                    skip = True
            # Check if the repo name is contained in the 'omit' list
            for o in omit:
                if o in it['name']:
                    skip = True
            # We have not processed this tool so create a list entry
            if not skip:
                ti = {'name': it['name'],
                      'owner': it['owner'],
                      'revisions': [it.get('changeset_revision', None)],
                      'tool_shed_url': 'https://' + it['tool_shed']}
                installed_revisions_list.append(ti)
    return installed_revisions_list


def installed_tools(gi, omit=None):
    """
    Get a list of tools on a Galaxy instance.
    :type gi: GalaxyInstance object
    :param gi: A GalaxyInstance object as retured by `galaxy_instance` method.
    :type omit: list of strings
    :param omit: A list of strings that, if found in a tool name, will result
                    in the tool not being included in the returned list.
    :rtype: dict
    :return: The returned dictionary contains the following keys, each
             containing a list of dictionaries:
                - `tool_panel_shed_tools` with a list of tools available in the
                tool panel that were installed on the target Galaxy instance
                from the Tool Shed;
                - `tool_panel_custom_tools` with a list of tools available in
                the tool panel that were not installed via the Tool Shed;
                - `shed_tools` with a list of tools returned from the
                `installed_tool_revisions` function and complemented with a
                `tool_panel_section_id` key as matched with the list of tools
                from the first element of the returned triplet. Note that the
                two lists (`shed_tools` and `tool_panel_shed_tools`) are likely
                to be different and hence not every element in the `shed_tools`
                will have the `tool_panel_section_id`!
    .. seealso:: `installed_tool_revisions` (this function also returns the
                 output of the `installed_tool_revisions` function, as
                 `shed_tools` key).
    """
    if not omit:
        omit = []
    tp_tools = []  # Tools available in the tool panel and installe via a TS
    custom_tools = []  # Tools available in the tool panel but custom-installed

    tl = gi.tools.get_tool_panel()  # In-panel tool list
    for ts in tl:  # ts -> tool section
        # print "%s (%s): %s" % (ts['name'], ts['id'], len(ts.get('elems', [])))
        # Parse the tool panel to ge the the tool lists
        for t in ts.get('elems', []):
            # Tool ID is either a tool name (in case of custom-installed tools)
            # or a URI (in case of Tool Shed-installed tools) so differentiate
            # among those
            tid = t['id'].split('/')
            if len(tid) > 3:
                skip = False
                # Check if we already encountered this tool
                for added_tool in tp_tools:
                    if tid[3] in added_tool['name']:
                        skip = True
                # Check if the repo name is contained in the 'omit' list
                for o in omit:
                    if o in tid[3]:
                        skip = True
                if not skip:
                    tp_tools.append({'tool_shed_url': "https://{0}".format(tid[0]),
                                     'owner': tid[2],
                                     'name': tid[3],
                                     'tool_panel_section_id': ts['id']})
            else:
                custom_tools.append(t['id'])

    # Match tp_tools with the tool list available from the Tool Shed Clients on
    # the given Galaxy instance and and add tool section IDs it
    ts_tools = installed_tool_revisions(gi, omit)  # Tools revisions installed via a TS
    for it in ts_tools:
        for t in tp_tools:
            if the_same_tool(it, t):
                it['tool_panel_section_id'] = t['tool_panel_section_id']

    return {'tool_panel_shed_tools': tp_tools,
            'tool_panel_custom_tools': custom_tools,
            'shed_tools': ts_tools}


def _list_tool_categories(tl):
    """
    Given a list of dicts `tl` as returned by the `installed_tools` method and
    where each list element holds a key `tool_panel_section_id`, return a list
    of unique section IDs.
    """
    category_list = []
    for t in tl:
        category_list.append(t.get('id'))
    return set(category_list)


def _parser():
    '''construct the parser object'''
    parent = get_common_args()
    parser = ArgumentParser(
        parents=[parent],
        usage="usage: python %(prog)s <options>")
    parser.add_argument("-d", "--dbkeysfile",
                        dest="dbkeys_list_file",
                        help="Reference genome dbkeys to install (see "
                             "dbkeys_list.yaml.sample)",)
    parser.add_argument("-t", "--toolsfile",
                        dest="tool_list_file",
                        help="Tools file to use (see tool_list.yaml.sample)",)
    parser.add_argument("-y", "--yaml_tool",
                        dest="tool_yaml",
                        help="Install tool represented by yaml string",)
    parser.add_argument("--name",
                        help="The name of the tool to install (only applicable "
                             "if the tools file is not provided).")
    parser.add_argument("--owner",
                        help="The owner of the tool to install (only applicable "
                             "if the tools file is not provided).")
    parser.add_argument("--section",
                        dest="tool_panel_section_id",
                        help="Galaxy tool panel section ID where the tool will "
                             "be installed (the section must exist in Galaxy; "
                             "only applicable if the tools file is not provided).")
    parser.add_argument("--section_label",
                        default=None,
                        dest="tool_panel_section_label",
                        help="Galaxy tool panel section label where tool will be installed "
                             "(if the section does not exist, it will be created; "
                             "only applicable if the tools file is not provided).")
    parser.add_argument("--toolshed",
                        dest="tool_shed_url",
                        help="The Tool Shed URL where to install the tool from. "
                             "This is applicable only if the tool info is "
                             "provided as an option vs. in the tools file.")
    parser.add_argument("--skip_install_tool_dependencies",
                        action="store_true",
                        dest="skip_tool_dependencies",
                        help="Skip the installation of tool dependencies using classic toolshed packages. "
                             "Can be overwritten on a per-tool basis in the tools file.")
    parser.add_argument("--install_resolver_dependencies",
                        action="store_true",
                        dest="install_resolver_dependencies",
                        help="Install tool dependencies through resolver (e.g. conda). "
                             "Will be ignored on galaxy releases older than 16.07. "
                             "Can be overwritten on a per-tool basis in the tools file")
    return parser


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parser = _parser()
    return parser.parse_args()


def _flatten_tools_info(tools_info):
    """
    Flatten the dict containing info about what tools to install.
    The tool definition YAML file allows multiple revisions to be listed for
    the same tool. To enable simple, iterattive processing of the info in this
    script, flatten the `tools_info` list to include one entry per tool revision.
    :type tools_info: list of dicts
    :param tools_info: Each dict in this list should contain info about a tool.
    :rtype: list of dicts
    :return: Return a list of dicts that correspond to the input argument such
             that if an input element contained `revisions` key with multiple
             values, those will be returned as separate list items.
    """
    def _copy_dict(d):
        """
        Iterrate through the dictionary `d` and copy its keys and values
        excluding the key `revisions`.
        """
        new_d = {}
        for k, v in d.items():
            if k != 'revisions':
                new_d[k] = v
        return new_d

    flattened_list = []
    for tool_info in tools_info:
        revisions = tool_info.get('revisions', [])
        if len(revisions) > 1:
            for revision in revisions:
                ti = _copy_dict(tool_info)
                ti['changeset_revision'] = revision
                flattened_list.append(ti)
        elif revisions:  # A single revisions was defined so keep it
            ti = _copy_dict(tool_info)
            ti['changeset_revision'] = revisions[0]
            flattened_list.append(ti)
        else:  # Revision was not defined at all
            flattened_list.append(tool_info)
    return flattened_list


def run_data_managers(options):
    """
    Run Galaxy Data Manager to download, index, and install reference genome
    data into Galaxy.
    :type options: OptionParser object
    :param options: command line arguments parsed by OptionParser
    """
    _ensure_log_configured()
    dbkeys_list_file = options.dbkeys_list_file
    kl = load_input_file(dbkeys_list_file)  # Input file contents
    dbkeys = kl['dbkeys']  # The list of dbkeys to install
    dms = kl['data_managers']  # The list of data managers to run
    options.galaxy_url = options.galaxy or kl['galaxy_instance']
    options.api_key = options.api_key or kl['api_key']

    gi = get_galaxy_connection(options)

    istart = dt.datetime.now()
    errored_dms = []
    dbkey_counter = 0
    for dbkey in dbkeys:
        dbkey_counter += 1
        dbkey_name = dbkey.get('dbkey')
        dm_counter = 0
        for dm in dms:
            dm_counter += 1
            dm_tool = dm.get('id')
            # Initiate tool installation
            start = dt.datetime.now()
            log.debug('[dbkey {0}/{1}; DM: {2}/{3}] Installing dbkey {4} with '
                      'DM {5}'.format(dbkey_counter, len(dbkeys), dm_counter,
                                      len(dms), dbkey_name, dm_tool))
            tool_input = dbkey
            try:
                response = gi.tools.run_tool('', dm_tool, tool_input)
                jobs = response.get('jobs', [])
                # Check if a job is actually running
                if len(jobs) == 0:
                    log.warning("\t(!) No '{0}' job found for '{1}'".format(dm_tool,
                                dbkey_name))
                    errored_dms.append({'dbkey': dbkey_name, 'DM': dm_tool})
                else:
                    # Monitor the job(s)
                    log.debug("\tJob running", extra={'same_line': True})
                    done_count = 0
                    while done_count < len(jobs):
                        done_count = 0
                        for job in jobs:
                            job_id = job.get('id')
                            job_state = gi.jobs.show_job(job_id).get('state', '')
                            if job_state == 'ok':
                                done_count += 1
                            elif job_state == 'error':
                                done_count += 1
                                errored_dms.append({'dbkey': dbkey_name, 'DM': dm_tool})
                        log.debug("", extra={'same_line': True})
                        time.sleep(10)
                    log.debug("\tDbkey '{0}' installed successfully in '{1}'".format(
                              dbkey.get('dbkey'), dt.datetime.now() - start))
            except ConnectionError as e:
                response = None
                end = dt.datetime.now()
                log.error("\t* Error installing dbkey {0} for DM {1} (after {2}): {3}"
                          .format(dbkey_name, dm_tool, end - start, e.body))
                errored_dms.append({'dbkey': dbkey_name, 'DM': dm_tool})
    log.info("All dbkeys & DMs listed in '{0}' have been processed.".format(dbkeys_list_file))
    log.info("Errored DMs: {0}".format(errored_dms))
    log.info("Total run time: {0}".format(dt.datetime.now() - istart))


def install_repository_revision(tool, tsc):
    """
    Adjusts tool dictionary to bioblend signature and installs single tool
    """
    _ensure_log_configured()
    tool['new_tool_panel_section_label'] = tool.pop('tool_panel_section_label')
    response = tsc.install_repository_revision(**tool)
    if isinstance(response, dict) and response.get('status', None) == 'ok':
        # This rare case happens if a tool is already installed but
        # was not recognised as such in the above check. In such a
        # case the return value looks like this:
        # {u'status': u'ok', u'message': u'No repositories were
        #  installed, possibly because the selected repository has
        #  already been installed.'}
        log.debug("\tTool {0} is already installed.".format(tool['name']))
    return response


def wait_for_install(tool, tsc, timeout=3600):
    """
    If nginx times out, we look into the list of installed repositories
    and try to determine if a tool of the same namer/owner is still installing.
    Returns True if install finished, returns False when timeout is exceeded.
    """
    def install_done(tool, tsc):
        itl = tsc.get_repositories()
        for it in itl:
            if (tool['name'] == it['name']) and (it['owner'] == tool['owner']):
                if it['status'] not in ['Installed', 'Error']:
                    return False
        return True

    finished = install_done(tool, tsc)
    while (not finished) and (timeout > 0):
        timeout -= 10
        time.sleep(10)
        finished = install_done(tool, tsc)
    if timeout > 0:
        return True
    else:
        return False


def get_install_tool_manager(options):
    """
    Parse the default input file and proceed to install listed tools.
    :type options: OptionParser object
    :param options: command line arguments parsed by OptionParser
    """
    install_tool_dependencies = INSTALL_TOOL_DEPENDENCIES
    install_repository_dependencies = INSTALL_REPOSITORY_DEPENDENCIES
    install_resolver_dependencies = INSTALL_RESOLVER_DEPENDENCIES

    tool_list_file = options.tool_list_file
    if tool_list_file:
        tl = load_input_file(tool_list_file)  # Input file contents
        tools_info = tl['tools']  # The list of tools to install
        install_repository_dependencies = tl.get('install_repository_dependencies', INSTALL_REPOSITORY_DEPENDENCIES)
        install_resolver_dependencies = tl.get('install_resolver_dependencies', INSTALL_RESOLVER_DEPENDENCIES)
        install_tool_dependencies = tl.get('install_tool_dependencies', INSTALL_TOOL_DEPENDENCIES)
    elif options.tool_yaml:
        tools_info = [yaml.load(options.tool_yaml)]
    else:
        # An individual tool was specified on the command line
        tools_info = [{"owner": options.owner,
                       "name": options.name,
                       "tool_panel_section_id": options.tool_panel_section_id,
                       "tool_panel_section_label": options.tool_panel_section_label,
                       "tool_shed_url": options.tool_shed_url or MTS}]

    galaxy_url = options.galaxy or tl.get('galaxy_instance')
    api_key = options.api_key or tl.get('api_key')

    if options.skip_tool_dependencies:
        install_tool_dependencies = False
        install_repository_dependencies = False
    elif tool_list_file:
        install_tool_dependencies = install_tool_dependencies
        install_repository_dependencies = install_repository_dependencies

    install_resolver_dependencies = options.install_resolver_dependencies or install_resolver_dependencies
    gi = get_galaxy_connection(options)
    if not gi:
        gi = galaxy_instance(galaxy_url, api_key)
    return InstallToolManager(tools_info=tools_info,
                              gi=gi,
                              default_install_tool_dependencies=install_tool_dependencies,
                              default_install_repository_dependencies=install_repository_dependencies,
                              default_install_resolver_dependencies=install_resolver_dependencies
                              )


class InstallToolManager(object):

    def __init__(self,
                 tools_info,
                 gi,
                 default_install_tool_dependencies=INSTALL_TOOL_DEPENDENCIES,
                 default_install_resolver_dependencies=INSTALL_RESOLVER_DEPENDENCIES,
                 default_install_repository_dependencies=INSTALL_REPOSITORY_DEPENDENCIES,
                 require_tool_panel_info=True):
        self.tools_info = tools_info
        self.gi = gi
        self.tsc = tool_shed_client(self.gi)
        self.require_tool_panel_info = require_tool_panel_info
        self.install_tool_dependencies = default_install_tool_dependencies
        self.install_resolver_dependencies = default_install_resolver_dependencies
        self.install_repository_dependencies = default_install_repository_dependencies
        self.errored_tools = []
        self.skipped_tools = []
        self.installed_tools = []

    def install_tools(self):
        """
        """
        _ensure_log_configured()
        istart = dt.datetime.now()
        itl = installed_tool_revisions(self.gi)  # installed tools list
        counter = 0
        tools_info = _flatten_tools_info(self.tools_info)
        total_num_tools = len(tools_info)
        default_err_msg = ('All repositories that you are attempting to install '
                           'have been previously installed.')

        # Process each tool/revision: check if it's already installed or install it
        for tool_info in tools_info:
            counter += 1
            already_installed = False  # Reset the flag
            tool = self.create_tool_install_payload(tool_info)
            if not tool:
                continue
            tool = self.get_changeset_revision(tool)
            if not tool:
                continue
            # Check if the tool@revision is already installed
            for installed in itl:
                if the_same_tool(installed, tool) and tool['changeset_revision'] in installed['revisions']:
                    log.debug("({0}/{1}) Tool {2} already installed at revision {3}. Skipping."
                              .format(counter, total_num_tools, tool['name'], tool['changeset_revision']))
                    self.skipped_tools.append({'name': tool['name'], 'owner': tool['owner'],
                                               'changeset_revision': tool['changeset_revision']})
                    already_installed = True
                    break
            if not already_installed:
                # Initiate tool installation
                start = dt.datetime.now()
                log.debug('(%s/%s) Installing tool %s from %s to section "%s" at '
                          'revision %s (TRT: %s)' %
                          (counter, total_num_tools, tool['name'], tool['owner'],
                           tool['tool_panel_section_id'] or tool['tool_panel_section_label'],
                           tool['changeset_revision'], dt.datetime.now() - istart))
                try:
                    install_repository_revision(tool, self.tsc)
                    log_tool_install_success(tool=tool, start=start, installed_tools=self.installed_tools)
                except ConnectionError as e:
                    if default_err_msg in e.body:
                        log.debug("\tTool %s already installed (at revision %s)" %
                                  (tool['name'], tool['changeset_revision']))
                    else:
                        if "504" in e.message:
                            log.debug("Timeout during install of %s, extending wait to 1h", tool['name'])
                            success = wait_for_install(tool=tool, tsc=self.tsc, timeout=3600)
                            if success:
                                log_tool_install_success(tool=tool, start=start, installed_tools=self.installed_tools)
                            else:
                                log_tool_install_error(tool=tool, start=start, msg=e.body, errored_tools=self.errored_tools)
                        else:
                            log_tool_install_error(tool=tool, start=start, msg=e.body, errored_tools=self.errored_tools)
        log.info("Installed tools ({0}): {1}".format(
                 len(self.installed_tools), [(t['name'], t.get('changeset_revision')) for t in self.installed_tools]))
        log.info("Skipped tools ({0}): {1}".format(
                 len(self.skipped_tools), [(t['name'], t.get('changeset_revision')) for t in self.skipped_tools]))
        log.info("Errored tools ({0}): {1}".format(
                 len(self.errored_tools), [(t['name'], t.get('changeset_revision', "")) for t in self.errored_tools]))
        log.info("All tools have been processed.")
        log.info("Total run time: {0}".format(dt.datetime.now() - istart))

    def create_tool_install_payload(self, tool_info):
        """
        For each listed tool (tool_info) we generate a payload that contains all
        required parameters, filling up missing parameters with user-defined and/or default settings.
        Return `None` if a required parameter is missing
        """
        tool = dict()  # Payload for the tool we are installing
        # Copy required `tool_info` keys into the `tool` dict
        tool['name'] = tool_info.get('name', None)
        tool['owner'] = tool_info.get('owner', None)
        tool['tool_panel_section_id'] = tool_info.get('tool_panel_section_id', None)
        tool['tool_panel_section_label'] = tool_info.get('tool_panel_section_label', None)
        # Check if all required tool sections have been provided; if not, skip
        # the installation of this tool. Note that data managers are an exception
        # but they must contain string `data_manager` within the tool name.
        now = dt.datetime.now()
        missing_required = not tool['name'] or not tool['owner']
        if not missing_required and self.require_tool_panel_info:
            if not (tool['tool_panel_section_id'] or tool['tool_panel_section_label']) and 'data_manager' not in tool.get('name', ''):
                log_tool_install_error(tool, start=now, msg='Tool panel section or tool panel name required',
                                       errored_tools=self.errored_tools)
                return None
        if not tool['name'] or not tool['owner']:
            log_tool_install_error(tool, start=now, msg="Missing required field", errored_tools=self.errored_tools)
            return None
        # Populate fields that can optionally be provided (if not provided, set
        # defaults).
        tool['install_tool_dependencies'] = \
            tool_info.get('install_tool_dependencies', self.install_tool_dependencies)
        tool['install_repository_dependencies'] = \
            tool_info.get('install_repository_dependencies', self.install_repository_dependencies)
        tool['install_resolver_dependencies'] = \
            tool_info.get('install_resolver_dependencies', self.install_resolver_dependencies)
        tool_shed = tool_info.get('tool_shed_url', MTS)
        if not tool_shed.endswith('/'):
            tool_shed += '/'
        if not tool_shed.startswith('http'):
            tool_shed = 'https://' + tool_shed
        tool['tool_shed_url'] = tool_shed
        tool['changeset_revision'] = tool_info.get('changeset_revision', None)
        return tool

    def get_changeset_revision(self, tool):
        """
        Select the correct changeset revision for a tool,
        and make sure the tool exists (i.e a request to the tool shed with name and owner returns a list of revisions).
        Return tool or None, if the tool could not be found on the specified tool shed.
        """
        ts = ToolShedInstance(url=tool['tool_shed_url'])
        # Get the set revision or set it to the latest installable revision
        installable_revisions = ts.repositories.get_ordered_installable_revisions(tool['name'], tool['owner'])
        if not installable_revisions:  # Repo does not exist in tool shed
            now = dt.datetime.now()
            log_tool_install_error(tool, start=now, msg="Repository does not exist in tool shed", errored_tools=self.errored_tools)
            return None
        if not tool['changeset_revision']:
            tool['changeset_revision'] = installable_revisions[-1]
        return tool


def script_main():
    global log
    _disable_external_library_logging()
    log = setup_global_logger(include_file=True)
    options = _parse_cli_options()
    if options.tool_list_file or options.tool_yaml or \
            options.name and options.owner and (options.tool_panel_section_id or options.tool_panel_section_label):
        itm = get_install_tool_manager(options)
        itm.install_tools()
        if itm.errored_tools:
            sys.exit(1)
    elif options.dbkeys_list_file:
        run_data_managers(options)
    else:
        sys.exit("Must provide a tool list file, individual tools info or a list of data manager tasks. "
                 "Look at usage.")


if __name__ == "__main__":
    script_main()
