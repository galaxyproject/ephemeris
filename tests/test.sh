#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

source $SCRIPT_DIR/test_library.sh

run-data-managers --help
shed-tools install --help
shed-tools update --help
workflow-install --help
setup-data-libraries --help
get-tool-list --help

source $TEST_DATA/test_shed_tools.sh
source $TEST_DATA/test_workflow_and_data.sh
source $TEST_DATA/test_run_data_managers.sh

