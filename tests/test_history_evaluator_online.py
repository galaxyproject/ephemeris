#!/usr/bin/env python

import os
from pathlib import Path

from ephemeris import history_evaluator

WF_URL = (
    "https://training.galaxyproject.org/training-material/topics/introduction/tutorials/galaxy-intro-short/"
    "workflows/Galaxy-Workflow-galaxy-intro-short.ga"
)
HIST_URL = "https://usegalaxy.eu/histories/view?id=19b7e0ced2125767"
APIKEY = os.getenv("GALAXY_API_KEY")


def test_get_hist_info():
    """ """
    galaxy_url, hist_name, hist_id = history_evaluator.get_hist_info(HIST_URL)
    assert galaxy_url == "https://usegalaxy.eu"
    assert hist_name == "Short Introduction for ghevaluator"
    assert hist_id == "19b7e0ced2125767"


def test_get_workflow_from_history():
    """ """
    wf = history_evaluator.get_workflow_from_history(HIST_URL, APIKEY)
    assert "a_galaxy_workflow" in wf and wf["a_galaxy_workflow"]
    assert "steps" in wf


def test_get_standard_workflow():
    """ """
    wf = history_evaluator.get_standard_workflow(WF_URL)
    assert "a_galaxy_workflow" in wf and wf["a_galaxy_workflow"]
    assert "steps" in wf


def test_is_input():
    """ """
    step = {
        "annotation": "",
        "content_id": None,
        "errors": None,
        "id": 0,
        "input_connections": {},
        "inputs": [{"description": "", "name": "mutant_R1"}],
        "label": "mutant_R1",
        "name": "mutant_R1",
        "outputs": [],
        "position": {"left": 10, "top": 10},
        "tool_id": None,
        "tool_state": '{"name": "mutant_R1"}',
        "tool_version": None,
        "type": "data_input",
        "uuid": "e271eee4-bfb8-40b4-b691-a25cb9932327",
        "workflow_outputs": [],
    }
    assert history_evaluator.is_input(step)
    step = {
        "annotation": "",
        "content_id": "toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72",
        "errors": None,
        "id": 1,
        "input_connections": {"input_file": {"id": 0, "output_name": "output"}},
        "inputs": [],
        "label": None,
        "name": "FastQC",
        "outputs": [{"name": "html_file", "type": "html"}, {"name": "text_file", "type": "txt"}],
        "position": {"left": 230, "top": 10},
        "post_job_actions": {},
        "tool_id": "toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72",
        "tool_shed_repository": {
            "changeset_revision": "c15237684a01",
            "name": "fastqc",
            "owner": "devteam",
            "tool_shed": "toolshed.g2.bx.psu.edu",
        },
        "tool_state": '{"__page__": null, "limits": "null", "input_file": "null", "__rerun_remap_job_id__": null, "contaminants": "null", "chromInfo": "\\"/cvmfs/data.galaxyproject.org/managed/len/ucsc/?.len\\""}',  # noqa: E501
        "tool_version": "0.72",
        "type": "tool",
        "uuid": "c6a231d9-786d-4fdf-bc25-8e3db1c16bfa",
        "workflow_outputs": [],
    }
    assert not history_evaluator.is_input(step)
    assert history_evaluator.is_input({"name": "Input dataset collection", "type": "data_collection_input"})


def test_count_wf_inputs():
    """ """
    wf = history_evaluator.get_standard_workflow(WF_URL)["steps"]
    assert history_evaluator.count_wf_inputs(wf) == 1


def test_get_input_id():
    """ """
    input_connections = {"input_file": {"id": 0, "output_name": "output"}}
    assert history_evaluator.get_input_id(input_connections) == [0]
    input_connections = {"output_name": "output"}
    assert history_evaluator.get_input_id(input_connections) == [-1]


def test_split_id():
    """ """
    tool_id = "toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72"
    owner, id, version = history_evaluator.split_id(tool_id)
    assert owner == "devteam"
    assert id == "fastqc"
    assert version == "0.72"
    tool_id = "toolshed.g2.bx.psu.edu/0.72"
    owner, id, version = history_evaluator.split_id(tool_id)
    assert owner is None
    assert id is None
    assert version is None


def test_reformate_workflows():
    """ """
    wf = history_evaluator.get_standard_workflow(WF_URL)["steps"]
    ordered_wf, wf_by_tools = history_evaluator.reformate_workflows(wf)
    assert isinstance(ordered_wf, list)
    assert isinstance(ordered_wf[0], dict)
    assert "tool" in ordered_wf[0]
    assert isinstance(ordered_wf[0]["inputs_connection"], list)
    assert isinstance(wf_by_tools, dict)
    assert "FastQC" in wf_by_tools
    assert isinstance(wf_by_tools["FastQC"], list)
    assert len(wf_by_tools["FastQC"]) == 1
    assert "tool" in wf_by_tools["FastQC"][0]


def test_fill_step_comparison():
    """ """
    key = "key"
    value = 1
    ref_step = {key: value}
    comparison = history_evaluator.fill_step_comparison(ref_step, None, key)
    assert isinstance(comparison, dict)
    assert "workflow" in comparison
    assert "history" in comparison
    assert "same" in comparison
    assert comparison["workflow"] == value
    assert comparison["history"] is None
    assert not comparison["same"]
    comparison = history_evaluator.fill_step_comparison(ref_step, ref_step, key)
    assert comparison["history"] == value
    assert comparison["same"]
    comparison = history_evaluator.fill_step_comparison(ref_step, {key: value + 1}, key)
    assert comparison["history"] == value + 1
    assert not comparison["same"]


def test_fill_step_report():
    """ """
    ref_step = {
        "tool": "tool",
        "id": "id",
        "owner": "owner",
        "version": "version",
        "parameters": {"p1": "p1"},
        "inputs_connection": [0],
        "order": 0,
    }
    report = history_evaluator.fill_step_report(ref_step, hist_step=None)
    assert isinstance(report, dict)
    assert "tool" in report
    assert "id" in report
    assert "owner" in report
    assert "version" in report
    assert "parameters" in report
    assert "inputs_connection" in report
    assert "order" in report
    assert isinstance(report["tool"], dict)
    assert "workflow" in report["tool"]
    assert report["tool"]["workflow"] == "tool"
    assert report["tool"]["history"] is None
    assert isinstance(report["parameters"], dict)
    assert "number" in report["parameters"]
    assert isinstance(report["parameters"]["number"], dict)
    assert report["parameters"]["number"]["workflow"] == 1
    assert report["parameters"]["number"]["history"] is None
    assert isinstance(report["parameters"]["details"], dict)
    assert "p1" in report["parameters"]["details"]
    assert report["parameters"]["details"]["p1"]["workflow"] == "p1"
    assert report["parameters"]["details"]["p1"]["history"] is None
    report = history_evaluator.fill_step_report(ref_step, ref_step)
    assert report["tool"]["history"] == "tool"
    assert report["parameters"]["number"]["history"] == 1
    assert report["parameters"]["details"]["p1"]["history"] == "p1"


def test_compare_ordered_steps():
    """ """
    ref_step = {
        "tool": "tool",
        "id": "id",
        "owner": "owner",
        "version": "version",
        "parameters": {"p1": "p1"},
        "inputs_connection": [0],
        "order": 0,
    }
    ref_steps = [ref_step]
    comparison = history_evaluator.compare_ordered_steps(ref_steps, None)
    assert isinstance(comparison, dict)
    assert len(comparison) == 1
    assert isinstance(comparison[0], dict)
    assert "tool" in comparison[0]
    assert comparison[0]["tool"]["history"] is None
    comparison = history_evaluator.compare_ordered_steps(ref_steps, ref_steps)
    assert comparison[0]["tool"]["history"] == "tool"
    hist_steps = [
        {
            "tool": "other-tool",
            "id": "id",
            "owner": "owner",
            "version": "version",
            "parameters": {"p1": "p1"},
            "inputs_connection": [0],
            "order": 0,
        },
        ref_step,
    ]
    comparison = history_evaluator.compare_ordered_steps(ref_steps, hist_steps)
    assert comparison[0]["tool"]["history"] is None


def test_compare_workflows():
    """ """
    ref_wf = history_evaluator.get_standard_workflow(WF_URL)
    hist_wf = history_evaluator.get_workflow_from_history(HIST_URL, APIKEY)
    report = history_evaluator.compare_workflows(hist_wf, ref_wf, {})
    assert isinstance(report, dict)
    assert "reference_wf" in report
    assert "history_wf" in report
    assert "data_inputs" in report
    assert isinstance(report["data_inputs"], dict)
    assert "workflow" in report["data_inputs"]
    assert report["data_inputs"]["workflow"] == 1
    assert report["data_inputs"]["history"] == 1
    assert report["data_inputs"]["same"]
    assert "steps" in report
    assert isinstance(report["steps"], dict)
    assert "workflow" in report["steps"]
    assert report["steps"]["workflow"] == 3
    assert report["steps"]["history"] == 3
    assert report["steps"]["same"]
    assert "comparison_given_reference_workflow_order" in report
    assert isinstance(report["comparison_given_reference_workflow_order"], dict)
    assert "comparison_by_reference_workflow_tools" in report
    assert isinstance(report["comparison_by_reference_workflow_tools"], dict)


def test_generate_html_report_content():
    """ """
    ref_wf = history_evaluator.get_standard_workflow(WF_URL)
    hist_wf = history_evaluator.get_workflow_from_history(HIST_URL, APIKEY)
    report = history_evaluator.compare_workflows(hist_wf, ref_wf, {"inputs": {"history": HIST_URL, "workflow": WF_URL}})
    content = history_evaluator.generate_html_report_content(report)
    assert "Galaxy History Evaluator report" in content
    assert "fa-check-square" in content
    assert "fa-exclamation-triangle" in content
    assert "FastQC" in content
    assert "1.0.2+galaxy0" in content
    assert "Occurrence 1" in content


def test_generate_report_files():
    """ """
    ref_wf = history_evaluator.get_standard_workflow(WF_URL)
    hist_wf = history_evaluator.get_workflow_from_history(HIST_URL, APIKEY)
    report = history_evaluator.compare_workflows(hist_wf, ref_wf, {"inputs": {"history": HIST_URL, "workflow": WF_URL}})
    history_evaluator.generate_report_files(report, Path("."))
    assert Path("report.json").exists()
    Path("report.json").unlink()
    assert Path("report.html").exists()
    Path("report.html").unlink()
    assert Path("report.md").exists()
    Path("report.md").unlink()


def test_evaluate_to_files():
    """ """
    history_evaluator.evaluate_to_files(HIST_URL, WF_URL, APIKEY, Path("."))
    assert Path("report.json").exists()
    Path("report.json").unlink()
    assert Path("report.html").exists()
    Path("report.html").unlink()
    assert Path("report.md").exists()
    Path("report.md").unlink()
