#!/usr/bin/env bash

set -eu
set -o pipefail

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export TEST_DATA=${EPHEMERIS_TEST_DATA:-"$CURRENT_DIR"}
# The exposed web port may change to 443 in the future
INTERNAL_EXPOSED_WEB_PORT=80


function start_container {
    # We start the image with the -P flag that published all exposed container ports
    # to random free ports on the host, since on OS X the container can't be reached
    # through the internal network (https://docs.docker.com/docker-for-mac/networking/#i-cannot-ping-my-containers)
    CID=$(docker run -d -e GALAXY_CONFIG_WATCH_TOOL_DATA_DIR=True -P bgruening/galaxy-stable:20.05)
    # We get the webport (https://docs.docker.com/engine/reference/commandline/inspect/#list-all-port-bindings)
    WEB_PORT=$(docker inspect --format="{{(index (index .NetworkSettings.Ports \"$INTERNAL_EXPOSED_WEB_PORT/tcp\") 0).HostPort}}" $CID)
    GALAXY_ADMIN_KEY="fakekey"
    GALAXY_ADMIN_PASSWORD="password"
    GALAXY_ADMIN_USER="admin@galaxy.org"
    GALAXY_URL="http://localhost:$WEB_PORT"
    echo "Wait for galaxy to start"
    galaxy-wait -g "${GALAXY_URL}" -a "${GALAXY_ADMIN_KEY}" --ensure_admin -v --timeout 180
    echo "Return from galaxy-wait $?"
}

function start_new_container {
    echo "Start new container"
    docker rm -f $CID
    start_container
}
