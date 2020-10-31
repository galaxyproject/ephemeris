#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

source $SCRIPT_DIR/test_library.sh

echo "Starting galaxy docker container"
start_container
docker ps

echo "Check workflow installation"
workflow-install --user admin@galaxy.org -p password -g "${GALAXY_URL}" -w "$TEST_DATA"/test_workflow.ga
workflow-install -a "$GALAXY_ADMIN_KEY" -g "${GALAXY_URL}" -w "$TEST_DATA"/test_workflow.ga

echo "Populate data libraries"
setup-data-libraries --user admin@galaxy.org -p password -g "${GALAXY_URL}" -i "$TEST_DATA"/library_data_example.yaml
setup-data-libraries -a "$GALAXY_ADMIN_KEY" -g "${GALAXY_URL}" -i "$TEST_DATA"/library_data_example.yaml
setup-data-libraries -a "$GALAXY_ADMIN_KEY" -g "${GALAXY_URL}" -i "$TEST_DATA"/library_data_example_legacy.yaml

echo "Get tool list from Galaxy"
get-tool-list -g "${GALAXY_URL}" -o result_tool_list.yaml
workflow-to-tools -w "$TEST_DATA"/test_workflow_2.ga -o result_workflow_to_tools.yaml

echo "Check tool installation from workflow"
shed-tools install -t result_workflow_to_tools.yaml -a "$GALAXY_ADMIN_KEY" -g "${GALAXY_URL}"
shed-tools install -t result_workflow_to_tools.yaml --user admin@galaxy.org -p password -g "${GALAXY_URL}"

docker rm -f $CID
