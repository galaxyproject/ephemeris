#!/usr/bin/env python
'''Tool to set permissions for all datasets of a given Galaxy Data Library'''

import argparse
import logging as log
from bioblend import galaxy
import sys, time, os

from .common_parser import get_common_args
# Print iterations progress
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Print New Line on Complete
    if iteration == total: 
        print()

def get_datasets(gi, library_id) -> [str]:
    objects = gi.libraries.show_dataset(library_id=library_id, dataset_id='')
    datasets = []
    for index in range(len(objects)):
       if objects[index]['type'] == 'file':
           datasets.append(objects[index]['id'])
    if datasets == []:
        sys.exit("No datasets in library!")
    else:
        return datasets

def set_permissions(gi, library_id, role_ids):
    log.info("Your library_id is " + library_id + "\n")
    log.info("Your roles are: %s", " ".join(role_ids))
    datasets = get_datasets(gi, library_id)
    total = len(datasets)
    est = total*3/60
    # Give User time to abort
    log.info('\nSuccess! %d datasets found. Processing can take up to %f min', total, est)
    t = 5
    while t:
        log.info('Starting in %d s ... Press Crtl+C to abort.', t)
        time.sleep(1)
        t -= 1
    # Process datasets
    for item in datasets:
        current = datasets.index(item) + 1
        log.debug('Processing dataset %d of %d, ID=%s', current, total, item)
        rows, columns = os.popen('stty size', 'r').read().split()
        printProgressBar(iteration=current, total=total, length=(int(columns) - 3))
        gi.libraries.set_dataset_permissions(dataset_id=item, access_in=role_ids, modify_in=role_ids, manage_in=role_ids)  

def _parser():
    '''Constructs the parser object'''
    parent = get_common_args()
    parser = argparse.ArgumentParser(
        parents=[parent],
        description='Populate the Galaxy data library with data.'
    )
    parser.add_argument('--library', help="Specify the data library ID")
    parser.add_argument('--roles', help="Specify a list of comma separated role IDs")
    return parser

def main():
    print("\nThis command script uses bioblend galaxyAPI to set ALL permissions of ALL datasets")
    print("in given library to given roles. Be careful and cancel with Crtl+C if unsure.\n")
    args = _parser().parse_args()
    if args.user and args.password:
        gi = galaxy.GalaxyInstance(url=args.galaxy, email=args.user, password=args.password)
    elif args.api_key:
        gi = galaxy.GalaxyInstance(url=args.galaxy, key=args.api_key)
    else:
        sys.exit('Please specify either a valid Galaxy username/password or an API key.')

    if args.verbose:
        log.basicConfig(level=log.DEBUG)
    else:
        log.basicConfig(level=log.INFO)
    
    if args.roles and args.library:
        args.roles = [r.strip() for r in args.roles.split(",")]
    else:
        sys.exit("Specify library ID (--library myLibraryID) and (list of) role(s) (--roles roleId1,roleId2)")
    set_permissions(gi, library_id=args.library, role_ids=args.roles)


if __name__ == '__main__':
    main()
