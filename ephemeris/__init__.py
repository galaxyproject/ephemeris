# -*- coding: utf-8 -*-

import yaml
from bioblend import galaxy


__version__ = '0.7.1.dev0'

PROJECT_NAME = "ephemeris"
PROJECT_OWNER = PROJECT_USERAME = "galaxyproject"
PROJECT_URL = "https://github.com/galaxyproject/ephemeris"
PROJECT_AUTHOR = 'Galaxy Project and Community'
PROJECT_EMAIL = 'jmchilton@gmail.com'
RAW_CONTENT_URL = "https://raw.github.com/%s/%s/master/" % (
    PROJECT_USERAME, PROJECT_NAME
)


def get_galaxy_connection(args):
    """
    Return a Galaxy connection, given a user or an API key.
    If either is missing returns `False`.
    """
    if args.user and args.password:
        return galaxy.GalaxyInstance(url=args.galaxy, email=args.user, password=args.password)
    elif args.api_key:
        return galaxy.GalaxyInstance(url=args.galaxy, key=args.api_key)
    return False


def load_yaml_file(filename):
    """
    Load YAML from the `tool_list_file` and return a dict with the content.
    """
    with open(filename, 'r') as f:
        dictionary = yaml.load(f)
    return dictionary


def dump_to_yaml_file(content, file_name):
    """
    Dump YAML-compatible `content` to `file_name`.
    """
    with open(file_name, 'w') as f:
        yaml.dump(content, f, default_flow_style=False)
