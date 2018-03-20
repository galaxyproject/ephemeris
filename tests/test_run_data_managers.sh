#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

source $SCRIPT_DIR/test_library.sh

echo "Starting galaxy docker container"
start_container
docker ps

echo "Installing data managers"
shed-tools install -t "$TEST_DATA"/data_manager_list.yaml -a admin -g http://localhost:$WEB_PORT

# Test whether get-tool-list is able to fetch data managers
echo "get-tool-list should not return data managers"
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list_post.yaml
grep -v data_manager result_tool_list_post.yaml
echo "get-tool-list with an api key should not return data managers"
get-tool-list -g http://localhost:$WEB_PORT -a admin -o result_tool_list_post.yaml
grep -v data_manager result_tool_list_post.yaml
echo "get-tool-list with an api_key and --get_data_mangers should return data managers"
get-tool-list -g http://localhost:$WEB_PORT -a admin --get_data_managers -o result_tool_list_post.yaml
grep data_manager result_tool_list_post.yaml

echo "Wait a few seconds before restarting galaxy"
sleep 15

echo "Restarting galaxy"
#We restart galaxy because otherwise the data manager tables won't be watched
docker exec $CID supervisorctl restart galaxy:

echo "Wait for galaxy to start"
galaxy-wait -g http://localhost:$WEB_PORT -v --timeout 120

echo "Check installation of reference genomes"
run-data-managers --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT --config "$TEST_DATA"/run_data_managers.yaml.test

#TODO: Implement test whether the indexers where launched simeltaneously

echo "Small waiting step to allow data-tables to update"
# This seems to be necessary on travis
sleep 15

echo "Check if installation is skipped when reference genomes are already installed."
run-data-managers -a admin -g http://localhost:$WEB_PORT --config "$TEST_DATA"/run_data_managers.yaml.test &> data_manager_output.txt
# Check if already installed was thrown
cat data_manager_output.txt

echo "Number of skipped jobs should be 9"
data_manager_already_installed=$(grep -i "Skipped jobs: 9" -c data_manager_output.txt)
if [ $data_manager_already_installed -ne 1 ]
    then
        echo "ERROR: Not all already installed genomes were skipped"
        exit 1
fi

docker rm -f $CID
