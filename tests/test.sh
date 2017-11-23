#!/usr/bin/env bash

set -eu
set -o pipefail

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_DATA=${EPHEMERIS_TEST_DATA:-"$CURRENT_DIR"}
# The exposed web port may change to 443 in the future
INTERNAL_EXPOSED_WEB_PORT=80

run-data-managers --help
shed-install --help
workflow-install --help
setup-data-libraries --help
get-tool-list --help

function start_container {
    # We start the image with the -P flag that published all exposed container ports
    # to random free ports on the host, since on OS X the container can't be reached
    # through the internal network (https://docs.docker.com/docker-for-mac/networking/#i-cannot-ping-my-containers)
    CID=`docker run -d -e GALAXY_CONFIG_WATCH_TOOL_DATA_DIR=True -P bgruening/galaxy-stable`
    # We get the webport (https://docs.docker.com/engine/reference/commandline/inspect/#list-all-port-bindings)
    WEB_PORT=`docker inspect --format="{{(index (index .NetworkSettings.Ports \"$INTERNAL_EXPOSED_WEB_PORT/tcp\") 0).HostPort}}" $CID`
    echo "Wait for galaxy to start"
    galaxy-wait -g http://localhost:$WEB_PORT -v --timeout 120
}

function start_new_container {
    echo "Start new container"
    docker rm -f $CID
    start_container
}

echo "Starting galaxy docker container"
start_container
docker ps

echo "Check tool installation with yaml on the commandline"
OLD_TOOL="{'owner':'jjohnson','tool_panel_section_id':'cdhit','name':'cdhit','revisions':['34a799d173f7']}"
shed-install -y  $OLD_TOOL --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "34a799d173f7" result_tool_list.yaml #installed revision

echo "TODO: Check update function"

start_new_container
echo "Check tool installation with command line flags"
shed-install --name cdhit --owner jjohnson --section cdhit --revisions "['34a799d173f7']" --a admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "34a799d173f7" result_tool_list.yaml #installed revision

start_new_container
echo "Check tool installation with --latest"
shed-install -y  $OLD_TOOL --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT --latest
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "28b7a43907f0" result_tool_list.yaml #latest revision

start_new_container
echo "Check tool installation from tool list"
# Establish the current tool list
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list_pre.yaml
shed-install -t "$TEST_DATA"/tool_list.yaml.sample -a admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list_post.yaml
grep 4d82cf59895e result_tool_list_post.yaml && grep 0b4e36026794 result_tool_list_post.yaml  # this means both revisions have been successfully installed.



echo "Wait a few seconds before restarting galaxy"
sleep 15

echo "Restarting galaxy"
#We restart galaxy because otherwise the data manager tables won't be watched
docker exec $CID supervisorctl restart galaxy:
echo "Wait for galaxy to start"
galaxy-wait -g http://localhost:$WEB_PORT -v --timeout 120

echo "Check workflow installation"
workflow-install --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT -w "$TEST_DATA"/test_workflow.ga
workflow-install -a admin -g http://localhost:$WEB_PORT -w "$TEST_DATA"/test_workflow.ga

echo "Populate data libraries"
setup-data-libraries --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT -i "$TEST_DATA"/library_data_example.yaml
setup-data-libraries -a admin -g http://localhost:$WEB_PORT -i "$TEST_DATA"/library_data_example.yaml

echo "Get tool list from Galaxy"
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
workflow-to-tools -w "$TEST_DATA"/test_workflow_2.ga -o result_workflow_to_tools.yaml

echo "Check tool installation from workflow"
shed-install -t result_workflow_to_tools.yaml -a admin -g http://localhost:$WEB_PORT
shed-install -t result_workflow_to_tools.yaml --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT

echo "Check installation of reference genomes"
run-data-managers --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT --config "$TEST_DATA"/run_data_managers.yaml.test

echo "Small waiting step to allow data-tables to update"
# This seems to be necessary on travis
sleep 15

echo "Check if installation is skipped when reference genomes are already installed."
run-data-managers -a admin -g http://localhost:$WEB_PORT --config "$TEST_DATA"/run_data_managers.yaml.test &> data_manager_output.txt
# Check if already installed was thrown
cat data_manager_output.txt

echo "Number of skipped jobs should be 6"
data_manager_already_installed=$(cat data_manager_output.txt | grep -i "Skipped jobs: 6" -c)
if [ $data_manager_already_installed -ne 1 ]
    then
        echo "ERROR: Not all already installed genomes were skipped"
        exit 1
fi

# Remove running container
docker rm -f $CID
