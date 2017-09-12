#!/bin/bash

set -e

run-data-managers --help
shed-install --help
workflow-install --help
setup-data-libraries --help
get-tool-list --help

echo "Check tool installation"
shed-install -t tests/tool_list.yaml.sample -a admin -g http://localhost:8080
shed-install -t tests/tool_list.yaml.sample --user admin@galaxy.org -p admin -g http://localhost:8080
echo "Check workflow installation"
workflow-install --user admin@galaxy.org -p admin -g http://localhost:8080 -w tests/test_workflow.ga
workflow-install -a admin -g http://localhost:8080 -w tests/test_workflow.ga
echo "Populate data libraries"
setup-data-libraries --user admin@galaxy.org -p admin -g http://localhost:8080 -i tests/library_data_example.yaml
setup-data-libraries -a admin -g http://localhost:8080 -i tests/library_data_example.yaml
echo "Get tool list from Galaxy"
get-tool-list -o result_tool_list.yaml
workflow-to-tools -w tests/test_workflow_2.ga -o result_workflow_to_tools.yaml
echo "Check tool installation from workflow"
shed-install -t result_workflow_to_tools.yaml -a admin -g http://localhost:8080
shed-install -t result_workflow_to_tools.yaml --user admin@galaxy.org -p admin -g http://localhost:8080
echo "Check installation of reference genomes"
run-data-managers --user admin@galaxy.org -p admin -g http://localhost:8080 --config tests/run_data_managers.yaml.test -v >> data_manager_first_run.txt 2>&1
echo $(cat data_manager_first_run.txt | grep -i "Running DM")
echo "Check if installation is skipped when reference genomes are already installed."
run-data-managers --user admin@galaxy.org -p admin -g http://localhost:8080 --config tests/run_data_managers.yaml.test -v >> data_manager_output.txt 2>&1
# Check if already installed was thrown
echo $(cat data_manager_output.txt | grep -i "already run for")
data_manager_already_installed=$(cat data_manager_output.txt | grep -i "already run for" -c)
if [ $data_manager_already_installed -ne 2 ]
    then
        echo "ERROR: Not all already installed genomes were skipped"
        exit 1
fi
