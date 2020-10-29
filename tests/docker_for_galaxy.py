from collections import namedtuple
from time import sleep

import docker
import pytest
from bioblend.galaxy import GalaxyInstance

from ephemeris.sleep import galaxy_wait


# It needs to work well with dev. Alternatively we can pin this to 'master' or another stable branch.
# Preferably a branch that updates with each stable release
GALAXY_IMAGE = "bgruening/galaxy-stable:20.05"
GALAXY_ADMIN_KEY = "fakekey"
GALAXY_ADMIN_PASSWORD = "password"
GALAXY_ADMIN_USER = "admin@galaxy.org"

client = docker.from_env()

GalaxyContainer = namedtuple('GalaxyContainer', ['url', 'container', 'attributes', 'gi'])


# Class scope is chosen here so we can group tests on the same galaxy in a class.
@pytest.fixture(scope="class")
def start_container(**kwargs):
    """Starts a docker container with the galaxy image. Returns a named tuple with the url, a GalaxyInstance object,
    the container attributes, and the container itself."""
    # We start a container from the galaxy image. We detach it. Port 80 is exposed to the host at a random port.
    # The random port is because we need mac compatibility. On GNU/linux a better option would be not to expose it
    # and use the internal ip address instead.
    # But alas, the trappings of a proprietary BSD kernel compel us to do ugly workarounds.

    container = client.containers.run(GALAXY_IMAGE, detach=True, ports={'80/tcp': None}, **kwargs)
    container_id = container.attrs.get('Id')
    print(container_id)

    # This seems weird as we also can just get container.attrs but for some reason
    # the network settings are not loaded in container.attrs. With the get request
    # these attributes are loaded
    container_attributes = client.containers.get(container_id).attrs

    # Venturing into deep nested dictionaries.
    exposed_port = container_attributes.get('NetworkSettings').get('Ports').get('80/tcp')[0].get('HostPort')

    container_url = "http://localhost:{0}".format(exposed_port)
    galaxy_wait(container_url,
                timeout=60)  # We are only going to wait 60 seconds. These are tests, and we are impatient!
    print("FOO!!!!!!!!!!\n\n\n\n\n\n\n\n\n\n")
    print(container.logs())
    sleep(300)
    yield GalaxyContainer(url=container_url,
                          container=container,
                          attributes=container_attributes,
                          gi=GalaxyInstance(container_url, key=GALAXY_ADMIN_KEY))
    container.remove(force=True)
