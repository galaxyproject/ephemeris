#!/bin/bash

set -e

run-data-managers --help
shed-install --help
workflow-install --help
setup-data-libraries --help
get-tool-list --help

shed-install -t tests/tool_list.yaml.sample --user admin@galaxy.org -p admin -g http://localhost:8080
workflow-install --user admin@galaxy.org -p admin -g http://localhost:8080 -w tests/test_workflow.ga 
setup-data-libraries --user admin@galaxy.org -p admin -g http://localhost:8080 -i tests/library_data_example.yaml
get-tool-list -o result_tool_list.yaml
