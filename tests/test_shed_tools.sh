#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

source $SCRIPT_DIR/test_library.sh
echo "Starting galaxy docker container"
start_container
docker ps

echo "Check tool installation with yaml on the commandline"
# CD Hit was chosen since it is old and seems to be unmaintained. Last update was 2015.
# Anyone know a smaller tool that could fit its place?
OLD_TOOL="{'owner':'jjohnson','name':'cdhit','revisions':['34a799d173f7'],'tool_panel_section_label':'CD_HIT'}"
shed-tools install -y  ${OLD_TOOL} --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "34a799d173f7" result_tool_list.yaml #installed revision

echo "Check update function"
shed-tools update -a admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "28b7a43907f0" result_tool_list.yaml #latest revision

start_new_container
echo "Check tool installation with command line flags"
shed-tools install --name cdhit --owner jjohnson --section_label "CD_HIT" --revisions 34a799d173f7 -a admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "34a799d173f7" result_tool_list.yaml #installed revision

start_new_container
echo "Check tool installation with --latest"
shed-tools install -y  $OLD_TOOL --user admin@galaxy.org -p admin -g http://localhost:$WEB_PORT --latest
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list.yaml
grep "cdhit" result_tool_list.yaml
grep "28b7a43907f0" result_tool_list.yaml #latest revision

start_new_container
echo "Check tool installation from tool list"
# Establish the current tool list
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list_pre.yaml
shed-tools install -t "$TEST_DATA"/tool_list.yaml.sample -a admin -g http://localhost:$WEB_PORT
get-tool-list -g http://localhost:$WEB_PORT -o result_tool_list_post.yaml
grep 4d82cf59895e result_tool_list_post.yaml && grep 0b4e36026794 result_tool_list_post.yaml  # this means both revisions have been successfully installed.

docker rm -f $CID
