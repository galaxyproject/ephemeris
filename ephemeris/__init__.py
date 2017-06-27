# -*- coding: utf-8 -*-

from bioblend import galaxy

__version__ = '0.7.0'

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
    """
    if args.user and args.password:
        gi = galaxy.GalaxyInstance(url=args.galaxy, email=args.user, password=args.password)
    elif args.api_key:
        gi = galaxy.GalaxyInstance(url=args.galaxy, key=args.api_key)

    return gi or False
