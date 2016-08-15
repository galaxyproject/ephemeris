#!/usr/bin/env python

import json
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import yaml


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parser = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
                            usage="python %(prog)s <options>",
                            epilog="example:\n"
                                   "python %(prog)s -w workflow1 workflow2 -o mytool_list.yml -l my_panel_label\n"
                                   "Christophe Antoniewski <drosofff@gmail.com>\n"
                                   "https://github.com/ARTbio/ansible-artimed/tree/master/extra-files/generate_tool_list_from_ga_workflow_files.py")
    parser.add_argument('-w', '--workflow',
                        dest="workflow_files",
                        required=True,
                        nargs='+',
                        help='A space separated list of galaxy workflow description files in json format', )
    parser.add_argument('-o', '--output-file',
                        required=True,
                        dest='output_file',
                        help='The output file with a yml tool list')
    parser.add_argument('-l', '--panel_label',
                        dest='panel_label',
                        default='Tools from workflows',
                        help='The name of the panel where the tools will show up in Galaxy.'
                             'If not specified: "Tools from workflows"')
    return parser.parse_args()


def get_workflow_dictionary(json_file):
    with open(json_file, "r") as File:
        mydict = json.load(File)[u'steps']
    return mydict


def translate_workflow_dictionary_to_tool_list(tool_dictionary, panel_label):
    starting_tool_list = []
    for step in tool_dictionary.values():
        tsr = step.get("tool_shed_repository")
        if tsr:
            starting_tool_list.append(tsr)
    tool_list = []
    for tool in starting_tool_list:
        sub_dic = {'name': tool['name'], 'owner': tool['owner'], 'revision': tool['changeset_revision'],
                   'tool_panel_section_label': panel_label, 'tool_shed_url': 'https://'+tool['tool_shed']}
        tool_list.append(sub_dic)
    return tool_list


def print_yaml_tool_list(tool_dictionary, output_file):
    with open(output_file, 'w') as F:
        F.write(yaml.safe_dump(tool_dictionary, default_flow_style=False))
    return


def generate_tool_list_from_workflow(workflow_files, panel_label, output_file):
    """

    :rtype: object
    """
    intermediate_tool_list = []
    for workflow in workflow_files:
        workflow_dictionary = get_workflow_dictionary(workflow)
        intermediate_tool_list += translate_workflow_dictionary_to_tool_list(workflow_dictionary, panel_label)
    reduced_tool_list = list({v['revision']: v for v in intermediate_tool_list}.values())
    convert_dic = {}
    convert_dic['tools'] = reduced_tool_list
    print_yaml_tool_list(convert_dic, output_file)

if __name__ == "__main__":
    options = _parse_cli_options()
    generate_tool_list_from_workflow(options.workflow_files, options.panel_label, options.output_file)
