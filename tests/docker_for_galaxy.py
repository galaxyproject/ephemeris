import docker
from docker.models.containers import Container
from collections import namedtuple
from ephemeris.sleep import

GALAXY_IMAGE = "bgruening/galaxy-stable:dev"

client = docker.from_env()

GalaxyContainer = namedtuple('GalaxyContainer', ['url', 'container', 'attributes'])


def start_container():
    # We start a container from the galaxy image. We detach it. Port 80 is exposed to the host at a random port.
    # The random port is because we need mac compatibility. On GNU/linux a better option would be not to expose it
    # and use the internal ip address instead.
    # But alas, the trappings of a proprietary BSD kernel compel us to do ugly workarounds.

    container = client.containers.run(GALAXY_IMAGE, detach=True, ports={'80/tcp': None})  # type: Container
    container_id = container.attrs.get('Id')
    print(container_id)

    # This seems weird as we also can just get container.attrs but for some reason
    # the network settings are not loaded in container.attrs. With the get request
    # these attributes are loaded
    container_attributes = client.containers.get(container_id).attrs

    # Venturing into deep nested dictionaries.
    exposed_port = container_attributes.get('NetworkSettings').get('Ports').get('80/tcp')[0].get('HostPort')

    container_url = "http://localhost:{0}".format(exposed_port)

    return GalaxyContainer(url=container_url, container=container, attributes=container_attributes)
