import pathlib
import tempfile

from ephemeris.generate_tool_list_from_ga_workflow_files import main as workflow_to_tools_cli
from ephemeris.get_tool_list_from_galaxy import main as get_tool_list_cli
from ephemeris.shed_tools import main as shed_tools_cli
from .conftest import GalaxyContainer

OLD_TOOL_YAML = "{'owner':'jjohnson','name':'cdhit','revisions':['34a799d173f7'],'tool_panel_section_label':'CD_HIT'}"

SAMPLE_TOOL_YAML_PATH = pathlib.Path(__file__).parent / "tool_list.yaml.sample"
WORKFLOW_PATH = pathlib.Path(__file__).parent / "test_workflow_2.ga"


def install_old_cdhit(start_container: GalaxyContainer):
    shed_tools_cli(
        [
            "install",
            "-y",
            OLD_TOOL_YAML,
            "--user",
            start_container.username,
            "--password",
            start_container.password,
            "-g",
            start_container.url,
        ]
    )


def get_tool_list(start_container: GalaxyContainer, *extra_args):
    with tempfile.NamedTemporaryFile(mode="r") as tool_list_file:
        get_tool_list_cli(["-g", start_container.url, "-o", tool_list_file.name, *extra_args])
        return tool_list_file.read()


def test_tool_install_yaml(start_container: GalaxyContainer):
    install_old_cdhit(start_container)
    tool_list = get_tool_list(start_container)
    assert "cdhit" in tool_list
    assert "34a799d173f7" in tool_list


def test_shed_tool_update(start_container: GalaxyContainer):
    install_old_cdhit(start_container)
    shed_tools_cli(["update", "-a", start_container.api_key, "-g", start_container.url])
    tool_list = get_tool_list(start_container)
    assert "cdhit" in tool_list
    assert "28b7a43907f0" in tool_list


def test_tool_install_with_command_line_flags(start_container: GalaxyContainer):
    shed_tools_cli(
        [
            "install",
            "--name",
            "cdhit",
            "--owner",
            "jjohnson",
            "--section-label",
            "CD_HIT",
            "--revisions",
            "34a799d173f7",
            "-a",
            start_container.api_key,
            "-g",
            start_container.url,
        ]
    )
    tool_list = get_tool_list(start_container)
    assert "cdhit" in tool_list
    assert "34a799d173f7" in tool_list


def test_install_with_latest_flag(start_container: GalaxyContainer):
    shed_tools_cli(
        [
            "install",
            "-y",
            OLD_TOOL_YAML,
            "--user",
            start_container.username,
            "-p",
            start_container.password,
            "-g",
            start_container.url,
            "--latest",
        ]
    )
    tool_list = get_tool_list(start_container)
    assert "cdhit" in tool_list
    assert "28b7a43907f0" in tool_list


def test_install_from_tool_list(start_container: GalaxyContainer):
    shed_tools_cli(
        [
            "install",
            "-t",
            str(SAMPLE_TOOL_YAML_PATH),
            "-a",
            start_container.api_key,
            "-g",
            start_container.url,
        ]
    )
    tool_list = get_tool_list(start_container, "--get_all_tools")
    assert "4d82cf59895e" in tool_list
    assert "0b4e36026794" in tool_list
    assert "051eba708f43" in tool_list


def test_workflows_to_tools_install(start_container: GalaxyContainer):
    with tempfile.NamedTemporaryFile() as tool_list_file:
        workflow_to_tools_cli(
            [
                "-w",
                str(WORKFLOW_PATH),
                "-o",
                tool_list_file.name,
            ]
        )
        shed_tools_cli(
            [
                "install",
                "-t",
                tool_list_file.name,
                "-a",
                start_container.api_key,
                "-g",
                start_container.url,
            ]
        )
