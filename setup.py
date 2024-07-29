#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ast
import os
import re

from setuptools import (
    find_packages,
    setup,
)

SOURCE_DIR = "src/ephemeris"

_version_re = re.compile(r"__version__\s+=\s+(.*)")


with open("%s/__init__.py" % SOURCE_DIR, "rb") as f:
    init_contents = f.read().decode("utf-8")

    def get_var(var_name):
        pattern = re.compile(r"%s\s+=\s+(.*)" % var_name)
        match = pattern.search(init_contents).group(1)
        return str(ast.literal_eval(match))

    version = get_var("__version__")
    PROJECT_NAME = get_var("PROJECT_NAME")
    PROJECT_URL = get_var("PROJECT_URL")
    PROJECT_AUTHOR = get_var("PROJECT_AUTHOR")
    PROJECT_EMAIL = get_var("PROJECT_EMAIL")

TEST_DIR = "tests"
PROJECT_DESCRIPTION = "Ephemeris is an opinionated library and set of scripts for managing the bootstrapping of Galaxy project plugins - tools, index data, and workflows."
ENTRY_POINTS = """
        [console_scripts]
        get-tool-list=ephemeris.get_tool_list_from_galaxy:main
        shed-tools=ephemeris.shed_tools:main
        workflow-install=ephemeris.workflow_install:main
        run-data-managers=ephemeris.run_data_managers:main
        workflow-to-tools=ephemeris.generate_tool_list_from_ga_workflow_files:main
        setup-data-libraries=ephemeris.setup_data_libraries:main
        galaxy-wait=ephemeris.sleep:main
        install_tool_deps=ephemeris.install_tool_deps:main
        install-tool-deps=ephemeris.install_tool_deps:main
        set-library-permissions=ephemeris.set_library_permissions:main
        _idc-lint=ephemeris._idc_lint:main
        _idc-split-data-manager-genomes=ephemeris._idc_split_data_manager_genomes:main
        _idc-data-managers-to-tools=ephemeris._idc_data_managers_to_tools:main
        """

PACKAGE_DATA = {
    # Be sure to update MANIFEST.in for source dist.
}
PACKAGE_DIR = {
    SOURCE_DIR: SOURCE_DIR,
}

readme = open("README.rst").read()
history = open("HISTORY.rst").read().replace(".. :changelog:", "")

if os.path.exists("requirements.txt"):
    requirements = open("requirements.txt").read().split("\n")
else:
    # In tox, it will cover them anyway.
    requirements = []


test_requirements = [
    # TODO: put package test requirements here
]


setup(
    name=PROJECT_NAME,
    version=version,
    description=PROJECT_DESCRIPTION,
    long_description=readme + "\n\n" + history,
    author=PROJECT_AUTHOR,
    author_email=PROJECT_EMAIL,
    url=PROJECT_URL,
    packages=find_packages("src"),
    entry_points=ENTRY_POINTS,
    package_data=PACKAGE_DATA,
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=requirements,
    license="AFL",
    zip_safe=False,
    python_requires=">=3.7",
    keywords="galaxy",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Environment :: Console",
        "License :: OSI Approved :: Academic Free License (AFL)",
        "Operating System :: POSIX",
        "Topic :: Software Development",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Testing",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    test_suite=TEST_DIR,
    tests_require=test_requirements,
)
