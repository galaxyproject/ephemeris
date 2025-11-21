import pathlib
import tempfile

import yaml

from ephemeris.generate_tool_list_from_ga_workflow_files import main as workflow_to_tools_cli

WORKFLOW_PATH = pathlib.Path(__file__).parent / "test_workflow_2.ga"
JSON_PATH = pathlib.Path(__file__).parent / "toolcats.json"


def test_workflows_to_tools_default():
    with tempfile.NamedTemporaryFile() as tool_list_file:
        workflow_to_tools_cli(
            [
                "-w",
                str(WORKFLOW_PATH),
                "-o",
                tool_list_file.name,
            ]
        )
        print(tool_list_file.name)
        with open(tool_list_file.name, "r") as file:
            result = yaml.safe_load(file)
    assert len(result["tools"]) == 2
    assert "jjohnson" in [t["owner"] for t in result["tools"]]
    assert "kellrott" in [t["owner"] for t in result["tools"]]


def test_workflows_to_tools_default_cat_json():
    with tempfile.NamedTemporaryFile() as tool_list_file:
        workflow_to_tools_cli(
            [
                "-w",
                str(WORKFLOW_PATH),
                "-o",
                tool_list_file.name,
                "-j",
                str(JSON_PATH),
            ]
        )
        print(tool_list_file.name)
        with open(tool_list_file.name, "r") as file:
            result = yaml.safe_load(file)
    assert len(result["tools"]) == 2
    assert "jjohnson" in [t["owner"] for t in result["tools"]]
    assert "kellrott" in [t["owner"] for t in result["tools"]]
    assert "Text Manipulation" in [t["tool_panel_section_label"] for t in result["tools"]]
