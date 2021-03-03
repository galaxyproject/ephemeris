import os
import random
import tempfile
import time
from collections import namedtuple
from pathlib import Path
from typing import Optional, Union

import docker
import jinja2
import pytest
from bioblend.galaxy import GalaxyInstance
from docker.models.containers import Container

from ephemeris.sleep import galaxy_wait


# It needs to work well with dev. Alternatively we can pin this to 'master' or another stable branch.
# Preferably a branch that updates with each stable release
GALAXY_IMAGE = "galaxy/galaxy-k8s:21.01"
GALAXY_ADMIN_KEY = "fakekey"
GALAXY_ADMIN_PASSWORD = "password"
GALAXY_ADMIN_USER = "admin@galaxy.org"

POSTGRES_IMAGE = "postgres:13"
NGINX_IMAGE = "nginx:1.18"
NGINX_TEMPLATE = Path(__file__).parent / "files" / "galaxy.nginx.j2"
CREATE_GALAXY_USER_PY = Path(__file__).parent / "files" / "create_galaxy_user.py"

client = docker.from_env()

GalaxyContainer = namedtuple('GalaxyContainer',
                             ['url', 'container', 'attributes', 'gi'])


def template_to_temp(template: Union[os.PathLike, str], **kwargs):
    template_string = Path(template).read_text()
    templated = jinja2.Template(template_string)
    with tempfile.NamedTemporaryFile('wt', delete=False) as temp_file:
        temp_file.write(templated.render(**kwargs))
    return temp_file.name


def get_container_url(container, port: str) -> str:
    container_attributes = client.containers.get(container.id).attrs
    network_settings = container_attributes.get('NetworkSettings')
    ports = network_settings.get('Ports')
    host_port = ports.get(port)[0].get('HostPort')
    return f"http://localhost:{host_port}"


class GalaxyService:

    def __init__(self,
                 api_key: Optional[str] = None):
        self.client = docker.from_env()
        self.id = hex(random.randint(0, 2**32-1)).lstrip("0x")
        self.network_name = f"galaxy_{self.id}"
        self.postgres_name = f"ephemeris_db_{self.id}"
        self.galaxy_web_name = f"galaxy_web_{self.id}"
        self.nginx_config = template_to_temp(NGINX_TEMPLATE,
                                             galaxy_web=self.galaxy_web_name)
        self.network = self.client.networks.create(self.network_name)
        self.postgres_container: Container = self.client.containers.run(
            POSTGRES_IMAGE, detach=True, network=self.network_name,
            name=self.postgres_name,
            environment=dict(
                POSTGRES_USER="dbuser",
                POSTGRES_ROOT_PASSWORD="secret",
                POSTGRES_PASSWORD="secret",
                POSTGRES_DB="galaxydb"
            ))
        self.galaxy_container: Container = self.client.containers.run(
            GALAXY_IMAGE, detach=True, network=self.network_name,
            name=self.galaxy_web_name,
            volumes=[f"{str(CREATE_GALAXY_USER_PY)}:/usr/local/bin/create_galaxy_user.py"],
            environment=dict(
                GALAXY_CONFIG_DATABASE_CONNECTION=f"postgresql://{self.postgres_name}/galaxydb?client_encoding=utf8",
                PGUSER="dbuser",
                PGPASSWORD="secret"
            ))
        time.sleep(2)  # We wait for the database to be created
        self.api_key = api_key or GALAXY_ADMIN_KEY
        result = self.galaxy_container.exec_run([
            "/galaxy/server/.venv/bin/python",
            "/usr/local/bin/create_galaxy_user.py",
            "--user", GALAXY_ADMIN_USER,
            "--username", "admin",
            "--key", self.api_key,
            "--password", GALAXY_ADMIN_PASSWORD,
            "-c", "/galaxy/server/config/galaxy.yml"
        ], workdir="/galaxy/server")
        if result.exit_code != 0:
            raise RuntimeError(f"Error when creating API Key: {result.output}")
        self.nginx_container: Container = self.client.containers.run(
            NGINX_IMAGE, detach=True, network=self.network_name,
            ports={'80/tcp': None},
            volumes=[f"{str(self.nginx_config)}:/etc/nginx/conf.d/default.conf"])
        self.url = get_container_url(self.nginx_container, '80/tcp')

    def stop(self, **kwargs):
        self.galaxy_container.stop(**kwargs)
        self.nginx_container.stop(**kwargs)
        self.postgres_container.stop(**kwargs)

    def remove(self, **kwargs):
        self.galaxy_container.remove(**kwargs)
        self.postgres_container.remove(**kwargs)
        os.remove(self.nginx_config)
        self.nginx_container.remove(**kwargs)

    def restart_galaxy(self):
        self.galaxy_container.restart()

    def __del__(self):
        self.remove(force=True)


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
    ensure_admin = kwargs.get("ensure_admin", True)

    container = client.containers.run(GALAXY_IMAGE, detach=True,
                                      ports={'80/tcp': None}, **kwargs)
    container_id = container.attrs.get('Id')
    print(container_id)

    # This seems weird as we also can just get container.attrs but for some reason
    # the network settings are not loaded in container.attrs. With the get request
    # these attributes are loaded
    container_attributes = client.containers.get(container_id).attrs

    # Venturing into deep nested dictionaries.
    exposed_port = container_attributes.get('NetworkSettings').get('Ports').get('80/tcp')[0].get('HostPort')

    container_url = "http://localhost:{0}".format(exposed_port)
    assert key
    ready = galaxy_wait(container_url,
                        timeout=180,
                        api_key=key,
                        ensure_admin=ensure_admin)
    if not ready:
        raise Exception("Failed to wait on Galaxy to start.")
    gi = GalaxyInstance(container_url, key=key)
    yield GalaxyContainer(url=container_url,
                          container=container,
                          attributes=container_attributes,
                          gi=gi)
    container.remove(force=True)
