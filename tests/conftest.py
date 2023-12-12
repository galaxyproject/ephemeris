from collections import namedtuple

import pytest
from bioblend.galaxy import GalaxyInstance
from galaxy.tool_util.verify.interactor import GalaxyInteractorApi
from galaxy_test.driver.driver_util import GalaxyTestDriver

GalaxyContainer = namedtuple("GalaxyContainer", ["url", "gi", "password", "username", "api_key"])


@pytest.fixture(scope="class")
def start_container(tmpdir_factory):
    config_dir = tmpdir_factory.mktemp("config")
    database = config_dir.join("universe.sqlite")
    test_driver = GalaxyTestDriver()
    test_driver.galaxy_config = {
        "job_config": {
            "runners": {
                "local": {
                    "load": "galaxy.jobs.runners.local:LocalJobRunner",
                    "workers": 1,
                }
            },
            "execution": {
                "default": "local_docker",
                "environments": {
                    "local_docker": {"runner": "local", "docker_enabled": True},
                },
            },
        },
        "admin_users": "test@bx.psu.edu",
        "bootstrap_admin_api_key": "123456789",
        "conda_auto_init": False,
        "config_dir": str(config_dir),
        "database_connection": f"sqlite:///{database}?isolation_level=IMMEDIATE",
    }
    test_driver.setup()
    server_wrapper = test_driver.server_wrappers[0]
    host = server_wrapper.host
    port = server_wrapper.port
    prefix = server_wrapper.prefix or ""
    url = f"http://{host}:{port}{prefix.rstrip('/')}/"
    interactor = GalaxyInteractorApi(galaxy_url=url, master_api_key="123456789", test_user="test@bx.psu.edu")
    gi = GalaxyInstance(url, key=interactor.api_key, password="testpass")
    try:
        yield GalaxyContainer(
            url=url,
            gi=gi,
            password="testpass",
            username="test@bx.psu.edu",
            api_key=interactor.api_key,
        )
    finally:
        test_driver.stop_servers()
