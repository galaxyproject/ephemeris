#!/usr/bin/env python

import json

from argparse import ArgumentDefaultsHelpFormatter
from argparse import ArgumentParser
from distutils.version import StrictVersion

import requests
import yaml

from .common_parser import get_common_args


class GiToToolYaml:
    def __init__(self, url,
                 output_file,
                 include_tool_panel_section_id=False,
                 skip_tool_panel_section_name=True,
                 skip_changeset_revision=False):

        self.url = url
        self.output_file = output_file
        self.include_tool_panel_section_id = include_tool_panel_section_id
        self.skip_tool_panel_section_name = skip_tool_panel_section_name
        self.skip_changeset_revision = skip_changeset_revision
        self.repository_list = self.get_repositories()
        self.merge_tool_changeset_revisions()
        self.filter_section_name_or_id_or_changeset()
        self.write_to_yaml()

    @property
    def toolbox(self):
        """
        Gets the toolbox elements from <galaxy_url>/api/tools
        """
        r = requests.get("{url}/api/tools".format(url=self.url))
        return json.loads(r.text)

    def get_repositories(self):
        """
        Toolbox elements returned by api/tools may be of class ToolSection or Tool.
        Parse these accordingly to get a list of repositories.
        """
        repositories = []
        for elem in self.toolbox:
            if elem['model_class'] == 'Tool':
                repositories.append(self.get_repo_from_tool(elem))
            elif elem['model_class'] == 'ToolSection':
                repositories.extend(self.get_repos_from_section(elem))
        return repositories

    def get_repo_from_tool(self, tool):
        """
        Get the minimum items required for re-installing a (list of) tools
        """
        if not tool.get('tool_shed_repository', None):
            return {}
        tsr = tool['tool_shed_repository']
        repo = {'name': tsr['name'],
                'owner': tsr['owner'],
                'tool_shed_url': tsr['tool_shed'],
                'revisions': [tsr['changeset_revision']],
                'tool_panel_section_id': tool['panel_section_id'],
                'tool_panel_section_label': tool['panel_section_name']}
        return repo

    def get_repos_from_section(self, section):
        repos = []
        for elem in section['elems']:
            if elem['model_class'] == 'Tool':
                repos.append(self.get_repo_from_tool(elem))
            elif elem['model_class'] == 'ToolSection':
                repos.extend(self.get_repos_from_section(elem))
        return [repo for repo in repos if repo]

    def merge_tool_changeset_revisions(self):
        """
        Each installed changeset revision of a tool is listed individually.
        Merge revisions of the same tool into a list.
        """
        tool_list = self.repository_list
        for current_tool in tool_list:
            for tool in tool_list:
                if current_tool is tool:
                    continue
                if (tool["name"] == current_tool['name']
                        and tool['owner'] == current_tool['owner']
                        and tool['tool_panel_section_id'] == current_tool['tool_panel_section_id']
                        and tool['tool_shed_url'] == current_tool['tool_shed_url']):
                    current_tool["revisions"].extend(tool["revisions"])
                    tool_list.remove(tool)
            current_tool['revisions'] = list(set(current_tool['revisions']))

    def filter_section_name_or_id_or_changeset(self):
        repo_list = []
        for repo in self.repository_list:
            if self.skip_tool_panel_section_name:
                del repo['tool_panel_section_label']
            if not self.include_tool_panel_section_id:
                del repo['tool_panel_section_id']
            if self.skip_changeset_revision:
                del repo['revisions']
            repo_list.append(repo)
        self.repository_list = repo_list

    def write_to_yaml(self):
        tool_dict = {"tools": self.repository_list}
        with open(self.output_file, "w") as output:
            output.write(yaml.safe_dump(tool_dict, default_flow_style=False))


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parent = get_common_args(login_required=False)
    parser = ArgumentParser(parents=[parent],
                            usage="usage: python %(prog)s <options>",
                            epilog='Example usage: python get_tool_yml_from_gi.py '
                                   '-g https://usegalaxy.org/ -o tool_list.yml',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("-o", "--output-file",
                        required=True,
                        dest="output",
                        help="tool_list.yml output file")
    parser.add_argument("-include_id", "--include_tool_panel_id",
                        action="store_true",
                        help="Include tool_panel_id in tool_list.yml ? "
                             "Use this only if the tool panel id already exists. See "
                             "https://github.com/galaxyproject/ansible-galaxy-tools/blob/master/files/tool_list.yaml.sample")
    parser.add_argument("-skip_name", "--skip_tool_panel_name",
                        action="store_true",
                        help="Do not include tool_panel_name in tool_list.yml ?")
    parser.add_argument("-skip_changeset", "--skip_changeset_revision",
                        action="store_true",
                        help="Do not include the changeset revision when generating the tool list."
                             "Use this if you would like to use the list to update all the tools in"
                             "your galaxy instance using shed-install."
                        )
    return parser.parse_args()


def check_galaxy_version(galaxy_url):
    version = requests.get("{url}/api/version".format(url=galaxy_url)).json()
    if StrictVersion(version['version_major']) < StrictVersion('16.04'):
        raise Exception('This script needs galaxy version 16.04 or newer')


def main():
    options = _parse_cli_options()
    check_galaxy_version(options.galaxy)
    GiToToolYaml(url=options.galaxy,
                 output_file=options.output,
                 include_tool_panel_section_id=options.include_tool_panel_id,
                 skip_tool_panel_section_name=options.skip_tool_panel_name,
                 skip_changeset_revision=options.skip_changeset_revision)


if __name__ == "__main__":
    main()
