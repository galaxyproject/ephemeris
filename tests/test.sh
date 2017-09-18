#!/usr/bin/env bash

set -e

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_DATA=${EPHEMERIS_TEST_DATA:-"$CURRENT_DIR"}
CID="galaxy-container"

run-data-managers --help
shed-install --help
workflow-install --help
setup-data-libraries --help
get-tool-list --help

echo "Starting galaxy docker container"
docker run --name $CID -d -e GALAXY_CONFIG_WATCH_TOOL_DATA_DIR=True -p 8080:80 bgruening/galaxy-stable
sleep 120s
docker ps
echo "Check tool installation"
shed-install -t "$TEST_DATA"/tool_list.yaml.sample -a admin -g http://localhost:8080
#shed-install -t "$TEST_DATA"/tool_list.yaml.sample --user admin@galaxy.org -p admin -g http://localhost:8080
#We restart galaxy because otherwise the data manager tables won't be watched
docker exec $CID supervisorctl restart galaxy: && sleep 60s
echo "Check workflow installation"
#workflow-install --user admin@galaxy.org -p admin -g http://localhost:8080 -w "$TEST_DATA"/test_workflow.ga
workflow-install -a admin -g http://localhost:8080 -w "$TEST_DATA"/test_workflow.ga
echo "Populate data libraries"
#setup-data-libraries --user admin@galaxy.org -p admin -g http://localhost:8080 -i "$TET_DATA"/library_data_example.yaml
setup-data-libraries -a admin -g http://localhost:8080 -i "$TEST_DATA"/library_data_example.yaml
echo "Get tool list from Galaxy"
get-tool-list -o result_tool_list.yaml
workflow-to-tools -w "$TEST_DATA"/test_workflow_2.ga -o result_workflow_to_tools.yaml
echo "Check tool installation from workflow"
shed-install -t result_workflow_to_tools.yaml -a admin -g http://localhost:8080
#shed-install -t result_workflow_to_tools.yaml --user admin@galaxy.org -p admin -g http://localhost:8080
echo "Check installation of reference genomes"
#run-data-managers --user admin@galaxy.org -p admin -g http://localhost:8080 --config ./run_data_managers.yaml.test -v
run-data-managers -a admin -g http://localhost:8080 --config "$TEST_DATA"/run_data_managers.yaml.test -v
echo "Check if installation is skipped when reference genomes are already installed."
run-data-managers -a admin -g http://localhost:8080 --config "$TEST_DATA"/run_data_managers.yaml.test -v >> data_manager_output.txt 2>&1
# Check if already installed was thrown
echo $(cat data_manager_output.txt | grep -i "already run for")
data_manager_already_installed=$(cat data_manager_output.txt | grep -i "already run for" -c)
if [ $data_manager_already_installed -ne 2 ]
    then
        echo "ERROR: Not all already installed genomes were skipped"
        exit 1
fi
# Remove running container
docker rm -f $CID
