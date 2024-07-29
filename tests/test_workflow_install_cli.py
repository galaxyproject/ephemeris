import pathlib

from ephemeris.workflow_install import main as workflow_install_cli
from .conftest import GalaxyContainer

TEST_WORKFLOW_PATH = pathlib.Path(__file__).parent / "test_workflow.ga"


def test_workflow_install_username_and_password(start_container: GalaxyContainer):
    workflow_install_cli(
        [
            "--user",
            start_container.username,
            "-p",
            start_container.password,
            "-g",
            start_container.url,
            "-w",
            str(TEST_WORKFLOW_PATH),
        ]
    )


def test_workflow_install_api_key(start_container: GalaxyContainer):
    workflow_install_cli(
        [
            "-a",
            start_container.api_key,
            "-g",
            start_container.url,
            "-w",
            str(TEST_WORKFLOW_PATH),
        ]
    )
