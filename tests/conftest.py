from collections import namedtuple

import docker
import pytest
from bioblend.galaxy import GalaxyInstance

from ephemeris.sleep import galaxy_wait

# It needs to work well with dev. Alternatively we can pin this to 'master' or another stable branch.
# Preferably a branch that updates with each stable release
DOCKER_IMAGE = "galaxy-min"  # or bgruening
GALAXY_IMAGE_MIN = "galaxy/galaxy-min:23.1-auto"
GALAXY_IMAGE_BGRUENING = "bgruening/galaxy-stable:20.05"
GALAXY_IMAGE = GALAXY_IMAGE_MIN if DOCKER_IMAGE == "galaxy-min" else GALAXY_IMAGE_BGRUENING
GALAXY_PORT = "80" if DOCKER_IMAGE == "bgruening" else "8080"
GALAXY_ADMIN_KEY = "fakekey"
GALAXY_ADMIN_PASSWORD = "password"
GALAXY_ADMIN_USER = "admin@galaxy.org"

GalaxyContainer = namedtuple(
    "GalaxyContainer", ["url", "container", "attributes", "gi"]
)


# Class scope is chosen here so we can group tests on the same galaxy in a class.
@pytest.fixture(scope="class")
def start_container(**kwargs):
    """Starts a docker container with the galaxy image. Returns a named tuple with the url, a GalaxyInstance object,
    the container attributes, and the container itself."""
    # We start a container from the galaxy image. We detach it. Port 80 is exposed to the host at a random port.
    # The random port is because we need mac compatibility. On GNU/linux a better option would be not to expose it
    # and use the internal ip address instead.
    # But alas, the trappings of a proprietary BSD kernel compel us to do ugly workarounds.
    key = kwargs.get("api_key", GALAXY_ADMIN_KEY)

    # Set this to False as we try to get bootstrap working with galaxy-min.
    # ensure_admin = kwargs.get("ensure_admin", True)
    ensure_admin = False

    client = docker.from_env()

    if DOCKER_IMAGE != "bgruening":
        if "environment" not in kwargs:
            kwargs["environment"] = {}
        environment = kwargs["environment"]
        environment["GALAXY_CONFIG_OVERRIDE_BOOTSTRAP_ADMIN_API_KEY"] = GALAXY_ADMIN_KEY
        environment["GALAXY_CONFIG_OVERRIDE_ADMIN_USERS"] = GALAXY_ADMIN_USER

    container = client.containers.run(
        GALAXY_IMAGE, detach=True, ports={f"{GALAXY_PORT}/tcp": None}, **kwargs
    )
    container_id = container.attrs.get("Id")
    print(container_id)

    # This seems weird as we also can just get container.attrs but for some reason
    # the network settings are not loaded in container.attrs. With the get request
    # these attributes are loaded
    container_attributes = client.containers.get(container_id).attrs

    # Venturing into deep nested dictionaries.
    exposed_port = (
        container_attributes.get("NetworkSettings")
        .get("Ports")
        .get(f"{GALAXY_PORT}/tcp")[0]
        .get("HostPort")
    )

    container_url = "http://localhost:{0}".format(exposed_port)
    assert key
    ready = galaxy_wait(
        container_url, timeout=180, api_key=key, ensure_admin=ensure_admin
    )
    if not ready:
        print(client.containers.get(container_id).logs())
        raise Exception("Failed to wait on Galaxy to start.")
    gi = GalaxyInstance(container_url, key=key)
    if DOCKER_IMAGE != "bgruening":
        user_dict = gi.users.create_local_user("admin", GALAXY_ADMIN_USER, GALAXY_ADMIN_PASSWORD)
        print(user_dict)
        gi = GalaxyInstance(container_url, email=GALAXY_ADMIN_USER,password=GALAXY_ADMIN_PASSWORD)

    yield GalaxyContainer(
        url=container_url, container=container, attributes=container_attributes, gi=gi
    )
    container.remove(force=True)
