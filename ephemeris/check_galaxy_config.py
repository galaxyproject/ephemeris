# coding=utf-8

import re

from argparse import ArgumentDefaultsHelpFormatter
from argparse import ArgumentParser
# from ConfigParser import ConfigParser


def check_galaxy_config(current_config_path, sample_config_path):
    # TODO: check config paths

    current_active_config, current_inactive_config = _parse_config(current_config_path)
    sample_active_config, sample_inactive_config = _parse_config(sample_config_path)

    new_default_configs = sorted([sample_active_config[key]
                                  for key in sample_active_config.keys()
                                  if key not in current_active_config.keys()],
                                 key=lambda config_option: config_option.line)
    if len(new_default_configs) > 0:
        print(u"New default configs discovered in %s" % sample_config_path)
        for config_option in new_default_configs:
            print(u"%s (line %s)" % (config_option.text, config_option.line))
        print(u"")

    new_config_options = sorted([sample_inactive_config[key]
                                 for key in sample_inactive_config.keys()
                                 if key not in current_inactive_config.keys() and
                                 key not in current_active_config.keys()],
                                key=lambda config_option: config_option.line)
    if len(new_config_options) > 0:
        print(u"New config options discovered in %s" % sample_config_path)
        for config_option in new_config_options:
            print(u"%s (line %s)" % (config_option.text, config_option.line))
        print(u"")

    deprecated_config_options = sorted([current_active_config[key]
                                        for key in current_active_config.keys()
                                        if key not in sample_active_config.keys() and
                                        key not in sample_inactive_config.keys()],
                                       key=lambda config_option: config_option.line)
    if len(deprecated_config_options) > 0:
        print(u"Deprecated config options present in %s" % current_config_path)
        for config_option in deprecated_config_options:
            print(u"%s (line %s)" % (config_option.text, config_option.line))


class ConfigOption(object):

    def __init__(self, key, value, text, line):
        self.key = key
        self.value = value
        self.text = text
        self.line = line


def _parse_config(config_path):

    active_config_pattern = r"^([^#]\S*)\s?=\s?(.*)$"
    inactive_config_pattern = r"^#(\S*)\s?=\s?(.*)$"

    active_config = {}
    inactive_config = {}

    parse = False
    position = 0

    with open(config_path) as current_config_file:
        for line in current_config_file:
            position += 1
            line = line.rstrip('\n')

            if not parse:
                if u"[app:main]" in line:
                    parse = True
                continue
            active_match = re.search(active_config_pattern, line)
            if active_match is not None:

                config_option = ConfigOption(key=active_match.group(1),
                                             value=active_match.group(2),
                                             text=line,
                                             line=position)

                active_config[active_match.group(1)] = config_option
            else:
                inactive_match = re.search(inactive_config_pattern, line)
                if inactive_match is not None:
                    config_option = ConfigOption(key=inactive_match.group(1),
                                                 value=inactive_match.group(2),
                                                 text=line,
                                                 line=position)
                    inactive_config[inactive_match.group(1)] = config_option

    return active_config, inactive_config


def _parse_cli_options():
    """
    Parse command line options, returning `parse_args` from `ArgumentParser`.
    """
    parser = ArgumentParser(usage="usage: %(prog)s <options>",
                            epilog='Example usage: check_galaxy_config '
                                   '-c galaxy/config/galaxy.ini -s galaxy/config/galaxy.ini.sample',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("-c", "--current_config",
                        required=True,
                        dest="current_config",
                        help="current galaxy config file path")
    parser.add_argument("-s", "--sample_config",
                        required=True,
                        dest="sample_config",
                        help="reference sample galaxy config file path")
    return parser.parse_args()


def main():
    options = _parse_cli_options()
    check_galaxy_config(current_config_path=options.current_config,
                        sample_config_path=options.sample_config)
