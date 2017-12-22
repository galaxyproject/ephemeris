#!/usr/bin/env python
"""Tool to extract a tool list from galaxy."""


from argparse import ArgumentDefaultsHelpFormatter
from argparse import ArgumentParser
from distutils.version import StrictVersion

import yaml
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.tools import ToolClient

from . import check_url
from .common_parser import get_common_args


class GiToToolYaml:
    def __init__(self, gi,
                 include_tool_panel_section_id=False,
                 skip_tool_panel_section_name=True,
                 skip_changeset_revision=False):

        self.gi = gi
        self.include_tool_panel_section_id = include_tool_panel_section_id
        self.skip_tool_panel_section_name = skip_tool_panel_section_name
        self.skip_changeset_revision = skip_changeset_revision
        self.repository_list = self.get_repositories()
        self.repository_list = self.merge_tool_changeset_revisions()
        self.filter_section_name_or_id_or_changeset()
        self.tool_list = {"tools": self.repository_list}

    @property
    def toolbox(self):
        """
        Gets the toolbox elements from <galaxy_url>/api/tools
        """
        tool_client = ToolClient(self.gi)
        return tool_client.get_tool_panel()

    def get_repositories(self):
        """
        Toolbox elements returned by api/tools may be of class ToolSection or Tool.
        Parse these accordingly to get a list of repositories.
        """
        repositories = []
        for elem in self.toolbox:
            if elem['model_class'] == 'Tool':
                repo = self.get_repo_from_tool(elem)
                if repo:
                    repositories.append(repo)
            elif elem['model_class'] == 'ToolSection':
                new_repos = self.get_repos_from_section(elem)
                if new_repos:
                    repositories.extend(new_repos)
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
                repo = self.get_repo_from_tool(elem)
                if repo:
                    repos.append(repo)
            elif elem['model_class'] == 'ToolSection':
                new_repos = self.get_repos_from_section(elem)
                if new_repos:
                    repos.extend(new_repos)
        return repos

    def merge_tool_changeset_revisions(self):
        """
        Each installed changeset revision of a tool is listed individually.
        Merge revisions of the same tool into a list.
        """
        repositories = {}
        repo_key_template = "{tool_shed_url}|{name}|{owner}|{tool_panel_section_id}|{tool_panel_section_label}"
        for i, tool in enumerate(self.repository_list):
            repo_key = repo_key_template.format(**tool)
            if repo_key in repositories:
                repositories[repo_key].extend(tool['revisions'])
            else:
                repositories[repo_key] = tool['revisions']
        new_repository_list = []
        for repo_key, changeset_revisions in repositories.items():
            changeset_revisions = list(set(changeset_revisions))
            tool_shed_url, name, owner, tool_panel_section_id, tool_panel_section_label = repo_key.split('|')
            new_repository_list.append(
                {'tool_shed_url': tool_shed_url,
                 'name': name,
                 'owner': owner,
                 'tool_panel_section_id': tool_panel_section_id,
                 'tool_panel_section_label': tool_panel_section_label,
                 'revisions': changeset_revisions}
            )
        return new_repository_list

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

    def write_to_yaml(self, output_file):
        with open(output_file, "w") as output:
            output.write(yaml.safe_dump(self.tool_list, default_flow_style=False))


def _parser():
    '''Creates the parser object.'''
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
    return parser


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parser = _parser()
    return parser.parse_args()


def check_galaxy_version(gi):
    version = gi.config.get_version()
    if StrictVersion(version['version_major']) < StrictVersion('16.04'):
        raise Exception('This script needs galaxy version 16.04 or newer')


def main():
    options = _parse_cli_options()
    galaxy_url = check_url(options.galaxy)
    gi = GalaxyInstance(galaxy_url)
    check_galaxy_version(gi)
    gi_to_tool_yaml = GiToToolYaml(
        gi=gi,
        include_tool_panel_section_id=options.include_tool_panel_id,
        skip_tool_panel_section_name=options.skip_tool_panel_name,
        skip_changeset_revision=options.skip_changeset_revision)
    gi_to_tool_yaml.write_to_yaml(options.output)


if __name__ == "__main__":
    main()
