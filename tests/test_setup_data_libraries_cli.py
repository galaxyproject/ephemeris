import pathlib

from ephemeris.setup_data_libraries import main as setup_data_libraries_cli
from .conftest import GalaxyContainer

LIBRARY_DATA_EXAMPLE = pathlib.Path(__file__).parent / "library_data_example.yaml"
LIBRARY_DATA_LEGACY_EXAMPLE = pathlib.Path(__file__).parent / "library_data_example_legacy.yaml"


def test_setup_data_libraries_with_username_and_password(
    start_container: GalaxyContainer,
):
    setup_data_libraries_cli(
        [
            "--user",
            start_container.username,
            "-p",
            start_container.password,
            "-g",
            start_container.url,
            "-i",
            str(LIBRARY_DATA_EXAMPLE),
        ]
    )


def test_setup_data_libraries_with_api_key(start_container: GalaxyContainer):
    setup_data_libraries_cli(
        [
            "-a",
            start_container.api_key,
            "-g",
            start_container.url,
            "-i",
            str(LIBRARY_DATA_EXAMPLE),
        ]
    )


def test_setup_data_libraries_legacy_with_api_key(start_container: GalaxyContainer):
    setup_data_libraries_cli(
        [
            "-a",
            start_container.api_key,
            "-g",
            start_container.url,
            "-i",
            str(LIBRARY_DATA_LEGACY_EXAMPLE),
        ]
    )
