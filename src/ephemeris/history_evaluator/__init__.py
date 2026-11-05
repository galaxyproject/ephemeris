"""Evaluate Galaxy histories by comparing them to a reference workflow or history.

Moved from ghevaluator (https://github.com/StreetScienceCommunity/ghevaluator) by Siyu Chen,
Teresa Müller and Bérénice Batut, MIT license (see LICENSE in this folder).
"""

import csv
import io
import json
import re
from pathlib import Path
from urllib import parse

from jinja2 import (
    Environment,
    PackageLoader,
    select_autoescape,
)

from ephemeris.history_evaluator.history import (  # noqa: F401
    api_get,
    build_workflow,
    fetch_dataset_text,
    galaxy_id,
    get_hist_info,
    get_workflow_from_history,
    id_from_redirect,
    load_history,
    SESSION,
    split_galaxy_url,
)
from ephemeris.history_evaluator.match import (  # noqa: F401
    clean_parameters,
    connection_ids,
    is_input_step,
    match_steps,
    same_connections,
    step_parameters,
    text_similarity,
    tool_key,
)

DEFAULT_GALAXY_URL = "https://usegalaxy.eu"


def key_for(url, apikey, galaxy_url):
    """
    Get the API key to use for a link: the key is only sent to its Galaxy server, not to a server
    named in a link (e.g. a link given by a student). Links on other servers are read without key,
    which works for published histories and histories shared via link.

    :param url: link the key would be sent to
    :param apikey: optional API key
    :param galaxy_url: Galaxy server of the API key, None to allow any server
    :return: the API key or None
    """

    def origin(u):
        parsed = parse.urlparse(u)
        return (
            parsed.scheme,
            (parsed.hostname or "").lower(),
            parsed.port or {"https": 443, "http": 80}.get(parsed.scheme),
        )

    if galaxy_url and origin(url) != origin(galaxy_url):
        return None
    return apikey


def get_standard_workflow(wf_url, apikey=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    Turn the workflow in a provided link into a dictionary, as the standard to be compared with the user workflow.

    :param wf_url: link to a workflow file, or to a Galaxy workflow (e.g. /published/workflow?id=... or /u/<username>/w/<slug>)
    :param apikey: optional API key, for a Galaxy workflow
    :param galaxy_url: Galaxy server of the API key
    :return: dictionary with the workflow
    """
    url = parse.urlparse(wf_url)
    wf_id = parse.parse_qs(url.query).get("id", [None])[0]
    if wf_id is None and re.search(r"/u/[^/]+/w/[^/]+/?$", url.path):
        wf_id = id_from_redirect(wf_url)
    if wf_id:
        server = split_galaxy_url(wf_url)[0]
        return api_get(
            server,
            f"workflows/{galaxy_id(wf_id, wf_url)}/download",
            key_for(wf_url, apikey, galaxy_url),
            params={"format": "json-download"},
        )
    r = SESSION.get(wf_url, timeout=60)
    r.raise_for_status()
    return r.json()


def is_input(step):
    """
    Check if a step is an input step

    :param step: dictionary with a workflow step
    :return: boolean
    """
    return is_input_step(step)


def count_wf_inputs(wf):
    """
    Count the numbers of the inputs in a workflow

    :param wf: a workflow
    :return: number of inputs in the workflow
    """
    return sum(1 for step in wf.values() if is_input(step))


def get_input_id(unkw_dict):
    """
    Recursive function looking for the id number inside the part of the dictionary of the input connections.

    :param unkw_dict: unknown layers of length of input connections as a sub dictionary
    :return: a list of integers representing the input id numbers
    """
    ids = []
    for item in unkw_dict.values():
        if isinstance(item, list):
            ids.extend(get_input_id(dict(enumerate(item))))
        elif isinstance(item, dict) and "id" in item:
            ids.append(item["id"])
        else:
            ids.append(-1)
    return ids


def split_id(tool_id):
    """
    Split the long tool id extracted from workflow into ToolShed owner, short tool id name, tool version

    :param tool_id: "content_id" from workflow file

    :return: owner, tool id, tool version
    """
    split_tool_id = str(tool_id).split("/")
    if len(split_tool_id) >= 6:
        owner = split_tool_id[2]
        id = split_tool_id[4]
        version = split_tool_id[5]
    else:
        owner = None
        id = None
        version = None
    return owner, id, version


def reformate_workflows(wf):
    """
    Reformate workflow steps into a list and a dictionary with key being the tool names

    :param wf: workflow steps
    :return: list and dictionary
    """
    ordered_wf = []
    wf_by_tools = {}
    for key, step in wf.items():
        if is_input(step):
            continue
        tool = step["name"]
        owner, id, version = split_id(step["tool_id"])
        step_dict = {
            "tool": tool,
            "id": id if id is not None else step["tool_id"],
            "owner": owner,
            "version": version if version is not None else step.get("tool_version"),
            "parameters": step_parameters(step),
            "inputs_connection": get_input_id(step["input_connections"]),
            "order": key,
        }
        ordered_wf.append(step_dict)
        wf_by_tools.setdefault(tool, [])
        wf_by_tools[tool].append(step_dict)
    return ordered_wf, wf_by_tools


def fill_step_comparison(ref_step, hist_step, key):
    """
    Compare reference and history steps for a specific key

    :param ref_step: dictionary with reference step
    :param hist_step: dictionary with history step
    :param key: key of values to compare
    :return: dictionary with workflow, history, same
    """
    hist_value = hist_step[key] if hist_step is not None else None
    return {"workflow": ref_step[key], "history": hist_value, "same": bool(ref_step[key] == hist_value)}


def fill_step_report(ref_step, hist_step=None):
    """
    Prepare the report for a step

    :param ref_step: dictionary with reference step
    :param hist_step: dictionary with history step
    :return: dictionary
    """
    s_report = {
        "tool": fill_step_comparison(ref_step, hist_step, "tool"),
        "id": fill_step_comparison(ref_step, hist_step, "id"),
        "owner": fill_step_comparison(ref_step, hist_step, "owner"),
        "version": fill_step_comparison(ref_step, hist_step, "version"),
        "order": fill_step_comparison(ref_step, hist_step, "order"),
        "parameters": {
            "number": {
                "workflow": len(ref_step["parameters"]),
                "history": len(hist_step["parameters"]) if hist_step is not None else None,
                "same": (
                    bool(len(ref_step["parameters"]) == len(hist_step["parameters"]))
                    if hist_step is not None
                    else False
                ),
            },
            "wrong": len(ref_step["parameters"]),
            "details": {},
        },
        "inputs_connection": fill_step_comparison(ref_step, hist_step, "inputs_connection"),
    }
    # compare parameters
    for p in ref_step["parameters"]:
        # a parameter missing in the history step is compared as empty
        s_report["parameters"]["details"][p] = {
            "workflow": ref_step["parameters"][p],
            "history": hist_step["parameters"].get(p) if hist_step is not None else None,
            "same": hist_step is not None and ref_step["parameters"][p] == hist_step["parameters"].get(p),
        }
        if s_report["parameters"]["details"][p]["same"]:
            s_report["parameters"]["wrong"] -= 1
    return s_report


def compare_ordered_steps(ref_steps, hist_steps):
    """
    Compare ordered steps, the step at the same position in both lists must use the same tool

    Kept for compatibility, `compare_workflows` matches steps with `match_steps`.

    :param ref_steps: list of steps in reference workflow
    :param hist_steps: list of steps in history workflow
    :return: dictionary with comparison
    """
    comparison = {}
    h_step_count = 0
    for i, ref_step in enumerate(ref_steps):
        if (
            hist_steps is not None
            and h_step_count < len(hist_steps)
            and ref_step["tool"] == hist_steps[h_step_count]["tool"]
        ):
            comparison[i] = fill_step_report(ref_step, hist_steps[h_step_count])
            h_step_count += 1
        else:
            comparison[i] = fill_step_report(ref_step, None)
    return comparison


def output_formats(step):
    """
    Get the formats of the outputs of a step from a history

    :param step: workflow step built from a history
    :return: sorted list of formats (collections as "collection")
    """
    return sorted(
        (o.get("extension") or "?") if o["type"] == "dataset" else "collection" for o in step.get("outputs", [])
    )


def step_score(step_report):
    """
    Score of a reference step: 0 if missing, 0.5 if the tool is found,
    up to 0.25 more for connections and 0.25 for parameters

    :param step_report: comparison of the step
    :return: number between 0 and 1
    """
    if step_report["status"] == "missing":
        return 0.0
    nb_params = step_report["parameters"]["number"]["workflow"]
    params = 1.0 if nb_params == 0 else 1 - step_report["parameters"]["wrong"] / nb_params
    return 0.5 + 0.25 * step_report["inputs_connection"]["same"] + 0.25 * params


def compare_final_outputs(ref_wf, hist_wf, fetch_text=None, nb_last=5):
    """
    Compare the output of the last step of a reference history to the outputs of the last steps of a history

    Steps are ordered by the end time of their job. Content is compared for the first dataset output,
    if `fetch_text` is given and the datasets are text.

    :param ref_wf: workflow built from the reference history
    :param hist_wf: workflow built from the history
    :param fetch_text: function (galaxy_url, dataset_id) -> text or None
    :param nb_last: number of last history steps to compare
    :return: dictionary with the comparison, None if the reference has no job end time
    """

    def last_steps(wf):
        # deleted steps are left out, unless all steps were deleted
        steps = [s for s in wf["steps"].values() if s["type"] == "tool" and s.get("end_time")]
        kept = [s for s in steps if not s.get("deleted") and not s.get("failed")] or steps
        return sorted(kept, key=lambda s: s["end_time"], reverse=True)

    ref_tools = last_steps(ref_wf)
    if not ref_tools:
        return None
    ref_last = ref_tools[0]
    hist_last = last_steps(hist_wf)[:nb_last]

    def first_dataset_text(wf, step):
        datasets = [o for o in step.get("outputs", []) if o["type"] == "dataset"]
        if fetch_text is None or not datasets:
            return None
        return fetch_text(wf["galaxy_url"], datasets[0]["id"])

    ref_text = first_dataset_text(ref_wf, ref_last)
    if fetch_text is None:
        note = "content not compared"
    elif ref_text is None:
        note = "reference output can not be read as text (e.g. purged, binary or a collection)"
    else:
        note = None
    candidates = []
    for step in hist_last:
        text = first_dataset_text(hist_wf, step) if ref_text is not None else None
        candidates.append(
            {
                "order": str(step["id"]),
                "tool": step["name"],
                "same_tool": tool_key(step["tool_id"]) == tool_key(ref_last["tool_id"]),
                "outputs": {
                    "workflow": len(ref_last["outputs"]),
                    "history": len(step["outputs"]),
                    "same": len(ref_last["outputs"]) == len(step["outputs"]),
                },
                "formats": {
                    "workflow": output_formats(ref_last),
                    "history": output_formats(step),
                    "same": output_formats(ref_last) == output_formats(step),
                },
                "content_similarity": round(text_similarity(ref_text, text), 3) if text is not None else None,
            }
        )
    similarities = [c["content_similarity"] for c in candidates if c["content_similarity"] is not None]
    return {
        "reference_step": {"order": str(ref_last["id"]), "tool": ref_last["name"], "formats": output_formats(ref_last)},
        "candidates": candidates,
        "best_content_similarity": max(similarities) if similarities else None,
        "tool_found": any(c["same_tool"] for c in candidates),
        "note": note,
    }


def compare_workflows(hist_wf, ref_wf, report, fetch_text=None):
    """
    Compare a history workflow to a reference workflow and generate a report

    The reference can be a workflow file or a workflow built from a reference history.
    With a reference history, output formats and the final outputs are compared too.

    :param hist_wf: dictionary with workflow built from the history
    :param ref_wf: dictionary with reference workflow
    :param report: dictionary to fill
    :param fetch_text: optional function (galaxy_url, dataset_id) -> text, to compare final output content
    :return: dictionary with report
    """
    hist_steps = hist_wf["steps"]
    ref_steps = ref_wf["steps"]
    matching = match_steps(ref_steps, hist_steps)
    mapping = matching["mapping"]
    # steps the tutor threw away (failed or deleted attempts) are not asked from the students
    scored_ref_steps = {k: s for k, s in ref_steps.items() if int(k) not in matching["thrown_away"]}
    ordered_hist_wf, _ = reformate_workflows(hist_steps)
    ordered_ref_wf, ref_wf_by_tool = reformate_workflows(scored_ref_steps)
    report["reference_wf"] = ordered_ref_wf
    report["history_wf"] = ordered_hist_wf
    # Compare inputs in both workflows
    hist_wf_input_nb = count_wf_inputs(hist_steps)
    ref_wf_input_nb = count_wf_inputs(ref_steps)
    report["data_inputs"] = {
        "workflow": ref_wf_input_nb,
        "history": hist_wf_input_nb,
        "same": bool(ref_wf_input_nb == hist_wf_input_nb),
    }
    # Compare number of steps in both workflows
    # thrown away steps (failed, or replaced attempts) are counted on neither side
    hist_away = set(matching["hist_thrown_away"])
    hist_step_nb = len(hist_steps) - hist_wf_input_nb - len(hist_away)
    ref_step_nb = len(scored_ref_steps) - ref_wf_input_nb
    report["steps"] = {"workflow": ref_step_nb, "history": hist_step_nb, "same": bool(ref_step_nb == hist_step_nb)}
    # Compare matched steps
    hist_by_order = {s["order"]: s for s in ordered_hist_wf}
    main_history = hist_wf.get("main_history_id")
    owner = hist_wf.get("user_id")
    # workflow files have outputs too, but with formats only known from the history
    ref_is_history = bool(ref_wf.get("history_id"))
    comparison = {}
    for i, ref_step in enumerate(ordered_ref_wf):
        raw_ref = ref_steps[ref_step["order"]]
        h = mapping.get(int(ref_step["order"]))
        raw_hist = hist_steps[str(h)] if h is not None else None
        s_report = fill_step_report(ref_step, hist_by_order[str(h)] if h is not None else None)
        s_report["status"] = "matched" if h is not None else "missing"
        s_report["inputs_connection"] = {
            "workflow": connection_ids(raw_ref),
            "history": connection_ids(raw_hist) if raw_hist else None,
            "same": bool(raw_hist and same_connections(raw_ref, raw_hist, mapping)),
        }
        s_report["cached"] = bool(raw_hist and raw_hist.get("cached"))
        s_report["cached_reference"] = bool(raw_ref.get("cached"))
        s_report["deleted"] = bool(raw_hist and raw_hist.get("deleted"))
        # collection elements whose job failed, for a step mapped over a collection
        s_report["failed_elements"] = raw_hist.get("failed_elements", 0) if raw_hist else 0
        s_report["elements"] = raw_hist.get("elements", 0) if raw_hist else 0
        copied_from = raw_hist.get("history_id") if raw_hist else None
        if raw_hist and raw_hist.get("inaccessible"):
            s_report["copied_from_history"] = "not accessible"
        else:
            s_report["copied_from_history"] = (
                copied_from if copied_from and main_history and copied_from != main_history else None
            )
        s_report["copied_by"] = copied_by(raw_hist, owner) if s_report["copied_from_history"] else None
        if raw_hist and ref_is_history:
            s_report["output_formats"] = {
                "workflow": output_formats(raw_ref),
                "history": output_formats(raw_hist),
                "same": output_formats(raw_ref) == output_formats(raw_hist),
            }
        comparison[i] = s_report
    report["comparison_given_reference_workflow_order"] = comparison
    # Compare workflows by tools, counting the runs of the history like the matching does:
    # by tool (not by name, which can change between versions), without thrown away runs
    by_tool = {}
    for tool, ref_tool_steps in ref_wf_by_tool.items():
        details = {}
        for j, ref_step in enumerate(ref_tool_steps):
            details[j] = next(c for i, c in comparison.items() if ordered_ref_wf[i] is ref_step)
        # tools with the same name (e.g. two Sort tools) are counted together
        keys = {tool_key(ref_steps[s["order"]]["tool_id"]) for s in ref_tool_steps}
        hist_runs = sum(
            1
            for k, s in hist_steps.items()
            if s.get("tool_id") and tool_key(s["tool_id"]) in keys and int(k) not in hist_away
        )
        by_tool[tool] = {
            "number": {"workflow": len(ref_tool_steps), "history": hist_runs, "same": len(ref_tool_steps) == hist_runs},
            "details": details,
        }
    report["comparison_by_reference_workflow_tools"] = by_tool
    # Steps of the history not in the reference
    report["extra_steps"] = [
        {
            "order": str(h),
            "tool": hist_steps[str(h)]["name"],
            "id": hist_by_order[str(h)]["id"],
            "version": hist_by_order[str(h)]["version"],
            "cached": bool(hist_steps[str(h)].get("cached")),
            "deleted": bool(hist_steps[str(h)].get("deleted")),
            "failed": bool(hist_steps[str(h)].get("failed")),
        }
        for h in matching["extra"]
    ]
    # Steps that failed or did not finish, also the ones matched to a failed attempt of the reference
    report["failed_steps"] = [
        {"order": k, "tool": s["name"]} for k, s in hist_steps.items() if s["type"] == "tool" and s.get("failed")
    ]
    # Steps whose job ran in another history, i.e. results copied from someone else,
    # or whose job can not be read, usually because it ran in a private history of someone else
    report["copied_steps"] = [
        {
            "order": k,
            "tool": s["name"],
            "history": "not accessible" if s.get("inaccessible") else s["history_id"],
            "by": copied_by(s, owner),
        }
        for k, s in hist_steps.items()
        if s.get("inaccessible") or (s.get("history_id") and main_history and s["history_id"] != main_history)
    ]
    # All jobs ran in another history: the history is a copy of a whole history
    report["history_id"] = hist_wf.get("history_id")
    report["main_history_id"] = main_history
    report["all_steps_from_history"] = (
        main_history if main_history and main_history != hist_wf.get("history_id") else None
    )
    # who ran the jobs of a copied whole history: only said when they were all run by one user
    runners = {s.get("user_id") for s in hist_steps.values() if s.get("history_id") == main_history}
    report["all_steps_by"] = (
        copied_by({"user_id": runners.pop()}, owner) if report["all_steps_from_history"] and len(runners) == 1 else None
    )
    if ref_is_history:
        report["final_outputs"] = compare_final_outputs(ref_wf, hist_wf, fetch_text)
    scores = [step_score(c) for c in comparison.values()]
    final = report.get("final_outputs") or {}
    report["score"] = {
        "steps": round(100 * sum(scores) / len(scores), 1) if scores else None,
        "final_output": (
            round(100 * final["best_content_similarity"], 1)
            if final.get("best_content_similarity") is not None
            else None
        ),
        "missing_steps": len(matching["missing"]),
        "extra_steps": sum(1 for s in report["extra_steps"] if not s["deleted"] and not s["failed"]),
        "deleted_steps": sum(1 for s in hist_steps.values() if s["type"] == "tool" and s.get("deleted")),
        "failed_steps": len(report["failed_steps"]),
        "copied_steps": len(report["copied_steps"]),
        "cached_steps": sum(1 for s in hist_steps.values() if s.get("cached")),
        "all_steps_from_history": report["all_steps_from_history"],
    }
    report["in_short"] = summarize_report(report)
    return report


def copied_by(step, owner):
    """
    Tell if a step of a history was run by the owner of the history

    :param step: workflow step with the `user_id` of its job
    :param owner: user id of the owner of the history
    :return: "same user", "another user", or None when the user of the job or the owner is not known
    """
    if not owner or not step or not step.get("user_id"):
        return None
    return "same user" if step["user_id"] == owner else "another user"


def count_names(names):
    """
    Join names, with the number of times a name is repeated

    :param names: list of names
    :return: text, e.g. "Sort (2 times), Group"
    """
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{n} ({c} times)" if c > 1 else n for n, c in counts.items())


def summarize_report(report):
    """
    Summarize a report in a few plain sentences, for tutors

    :param report: dictionary with report from `compare_workflows`
    :return: list of sentences
    """
    steps = list(report["comparison_given_reference_workflow_order"].values())
    matched = [s for s in steps if s["status"] == "matched"]
    missing = [s["tool"]["workflow"] for s in steps if s["status"] == "missing"]
    sentences = []
    if report.get("all_steps_from_history"):
        by = {"same user": " of the same user", "another user": " of another user"}.get(report.get("all_steps_by"), "")
        sentences.append(
            f"No step ran in this history, most ran in history {report['all_steps_from_history']}: this is a copy of a whole history{by}."
        )
    if missing:
        sentences.append(f"{len(matched)} of {len(steps)} steps done. Missing: {count_names(missing)}.")
    else:
        sentences.append(f"All {len(steps)} steps done.")
    params = [f"{s['tool']['workflow']} ({s['parameters']['wrong']})" for s in matched if s["parameters"]["wrong"]]
    if params:
        sentences.append(f"Different settings (number of parameters): {', '.join(params)}.")
    inputs = [s["tool"]["workflow"] for s in matched if not s["inputs_connection"]["same"]]
    if inputs:
        sentences.append(f"Run on other inputs than in the reference: {count_names(inputs)}.")
    formats = [s["tool"]["workflow"] for s in matched if s.get("output_formats") and not s["output_formats"]["same"]]
    if formats:
        sentences.append(f"Other output formats: {count_names(formats)}.")
    extra = [s["tool"] for s in report["extra_steps"] if not s["deleted"] and not s["failed"]]
    if extra:
        sentences.append(f"Extra steps: {count_names(extra)}.")
    failed = [s["tool"] for s in report.get("failed_steps", [])]
    if failed:
        sentences.append(f"Failed or not finished, so not counted as done: {count_names(failed)}.")
    for by, text in (
        ("another user", "Results copied from a history of another user"),
        ("same user", "Results copied from another history of the same user"),
        (None, "Results copied from another history"),
    ):
        copied = [s["tool"] for s in report["copied_steps"] if s.get("by") == by]
        if copied:
            sentences.append(f"{text}: {count_names(copied)}.")
    partly_failed = [
        f"{s['tool']['workflow']} ({s['failed_elements']} of {s['elements']})"
        for s in matched
        if s.get("failed_elements")
    ]
    if partly_failed:
        sentences.append(f"Some collection elements failed: {', '.join(partly_failed)}.")
    cached = report["score"]["cached_steps"]
    if cached:
        sentences.append(f"{cached} step{'s' if cached > 1 else ''} reused the result of an earlier job (job cache).")
    final = report.get("final_outputs")
    if final and final.get("best_content_similarity") is not None:
        sentences.append(f"Final result {round(100 * final['best_content_similarity'])} % similar to the reference.")
    return sentences


SCORE_EXPLANATION = (
    "How the step score works: every step of the reference is worth 100 points. A step done in the history gets 50 points, "
    "25 more if it was run on the same inputs as in the reference, and up to 25 more for the same settings (each setting "
    "counts the same, so 1 different setting out of 4 costs 6.25 points). A missing step gets 0 points. The step score is "
    "the average over all steps of the reference. A different tool version is shown but does not lower the score."
)


def get_template_env():
    """
    Get the Jinja environment with the report templates
    """
    env = Environment(
        loader=PackageLoader("ephemeris.history_evaluator", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html",)),
    )
    env.globals["score_explanation"] = SCORE_EXPLANATION
    return env


def generate_html_report_content(data):
    """
    Generate HTML report

    :param data: dictionary holding the information of the status of key features of user history
    """
    return get_template_env().get_template("report.html").render(report=data)


def generate_markdown_report_content(data):
    """
    Generate Markdown report

    :param data: dictionary holding the information of the status of key features of user history
    """
    return get_template_env().get_template("report.md").render(report=data)


def generate_report_files(data, output_dp):
    """
    Convert the report dictionary into a JSON file, a HTML file and a Markdown file

    :param data: dictionary holding the information of the status of key features of user history
    :param output_dp: Path object of the output directory
    """
    output_dp.mkdir(parents=True, exist_ok=True)

    json_fp = output_dp / Path("report.json")
    with json_fp.open("w") as out_f:
        json.dump(data, out_f, ensure_ascii=False, indent=4)

    html_fp = output_dp / Path("report.html")
    with html_fp.open("w") as out_f:
        out_f.write(generate_html_report_content(data))

    md_fp = output_dp / Path("report.md")
    with md_fp.open("w") as out_f:
        out_f.write(generate_markdown_report_content(data))


def is_workflow_url(url):
    """
    Check if a URL points to a workflow file rather than to a history

    :param url: URL
    :return: boolean
    """
    path = parse.urlparse(url).path
    return path.endswith((".ga", "/workflow")) or "/workflows/" in path or bool(re.search(r"/u/[^/]+/w/[^/]+/?$", path))


def get_reference(ref_url, apikey=None, ref_type=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    Get the reference workflow from a workflow URL or a history URL

    :param ref_url: URL to a workflow file (.ga), a Galaxy workflow or a Galaxy history
    :param apikey: optional API key for a history
    :param ref_type: 'workflow' or 'history', guessed from the URL if not given
    :param galaxy_url: Galaxy server of the API key
    :return: workflow dictionary and reference type ('workflow' or 'history')
    """
    ref_type = ref_type or ("workflow" if is_workflow_url(ref_url) else "history")
    if ref_type == "workflow":
        return get_standard_workflow(ref_url, apikey, galaxy_url), "workflow"
    return get_workflow_from_history(ref_url, key_for(ref_url, apikey, galaxy_url)), "history"


def evaluate(hist_url, ref_url, apikey=None, ref_wf=None, ref_type=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    Compare a history to a reference and return the report

    :param hist_url: URL to Galaxy history
    :param ref_url: URL to reference workflow or reference history
    :param apikey: optional Galaxy API key
    :param ref_wf: optional reference already loaded with `get_reference`, as (workflow, type)
    :param ref_type: 'workflow' or 'history', guessed from the URL if not given
    :param galaxy_url: Galaxy server of the API key, the key is not sent to other servers
    :return: dictionary with report
    """
    ref, ref_type = ref_wf if ref_wf is not None else get_reference(ref_url, apikey, ref_type, galaxy_url)
    hist_wf = get_workflow_from_history(hist_url, key_for(hist_url, apikey, galaxy_url))
    report = {"inputs": {"history": hist_url, "workflow": ref_url, "reference": ref_url, "reference_type": ref_type}}
    return compare_workflows(
        hist_wf, ref, report, fetch_text=lambda url, ds: fetch_dataset_text(url, ds, key_for(url, apikey, galaxy_url))
    )


def evaluate_to_files(hist_url, wf_url, apikey, output_dp, ref_type=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    The main function: compare a history to a reference and write the report files

    :param hist_url: URL to Galaxy history
    :param wf_url: URL to reference workflow or reference history
    :param apikey: a Galaxy API key, optional for published or shared histories
    :param output_dp: Path object of the output report
    :param ref_type: 'workflow' or 'history', guessed from the URL if not given
    :param galaxy_url: Galaxy server of the API key, the key is not sent to other servers
    """
    generate_report_files(evaluate(hist_url, wf_url, apikey, ref_type=ref_type, galaxy_url=galaxy_url), output_dp)


def read_students_csv(csv_fp, galaxy_url):
    """
    Read the list of histories to evaluate

    Columns (case insensitive): student name (or student), stud hist id (or student_history),
    ref hist id (or ref_history) and an optional tutorial name. History columns can be history ids
    or URLs, the reference can also be a URL to a workflow file.

    :param csv_fp: path to the CSV file
    :param galaxy_url: Galaxy URL used for history ids
    :return: list of dictionaries with student, tutorial, history and reference URLs
    """

    def to_url(value):
        value = value.strip()
        return value if value.startswith("http") else f"{galaxy_url.rstrip('/')}/histories/view?id={value}"

    # Excel saves "CSV UTF-8" with a byte order mark (utf-8-sig), and in some languages (e.g. German)
    # "CSV" with ";" and the Windows encoding
    raw = Path(csv_fp).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    columns = {(c or "").strip().lower() for c in reader.fieldnames or []}
    if not columns & {"stud hist id", "student_history"}:
        raise ValueError(f"No column 'stud hist id' in {csv_fp}, the columns are: {', '.join(sorted(columns))}")
    rows = []
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if isinstance(v, str) or v is None}
        student = row.get("student name") or row.get("student")
        hist = row.get("stud hist id") or row.get("student_history")
        ref = row.get("ref hist id") or row.get("ref_history")
        if not (student and hist and ref):
            continue
        rows.append(
            {
                "student": student,
                "tutorial": row.get("tutorial name", ""),
                "history": to_url(hist),
                "reference": to_url(ref),
            }
        )
    return rows


def safe_name(name):
    """
    Turn a name into a folder name

    :param name: any name
    :return: name with only letters, digits, - and _
    """
    return re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE).strip("_") or "history"


def evaluate_histories(rows, output_dp, apikey=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    Evaluate several histories and write one report per history and an overview

    :param rows: list of dictionaries with `student`, `history` (URL), `reference` (URL) and optional `tutorial`
    :param output_dp: Path object of the output directory
    :param apikey: optional Galaxy API key
    :param galaxy_url: Galaxy server of the API key, histories on other servers are not evaluated with the key
    :return: list of overview rows
    """

    def write_overview():
        output_dp.mkdir(parents=True, exist_ok=True)
        with (output_dp / "overview.json").open("w") as out_f:
            json.dump(overview, out_f, ensure_ascii=False, indent=4)
        with (output_dp / "overview.md").open("w") as out_f:
            out_f.write(generate_overview_content(overview))

    references = {}
    overview = []
    folders = set()
    for row in rows:
        folder = safe_name(row["student"] + (f"_{row['tutorial']}" if row.get("tutorial") else ""))
        base, n = folder, 1
        while folder in folders:
            n += 1
            folder = f"{base}_{n}"
        folders.add(folder)
        entry = dict(row, history_id=None, report=f"{folder}/report.md", score=None, in_short=[], error=None)
        try:
            if row["reference"] not in references:
                # a reference that can not be loaded is not tried again for each history
                try:
                    references[row["reference"]] = get_reference(row["reference"], apikey, galaxy_url=galaxy_url)
                except Exception as e:
                    references[row["reference"]] = e
            if isinstance(references[row["reference"]], Exception):
                raise references[row["reference"]]
            report = evaluate(
                row["history"], row["reference"], apikey, references[row["reference"]], galaxy_url=galaxy_url
            )
            generate_report_files(report, output_dp / folder)
            entry["history_id"] = report["history_id"]
            entry["score"] = report["score"]
            entry["in_short"] = report["in_short"]
        except Exception as e:  # keep going with the other histories
            entry["error"] = str(e)
        overview.append(entry)
        # written after each history, so an interrupted run keeps the histories already evaluated
        write_overview()
    if not overview:
        write_overview()
    return overview


def generate_overview_content(overview):
    """
    Generate the Markdown overview of several evaluated histories

    :param overview: list of overview rows from `evaluate_histories`
    """
    return get_template_env().get_template("overview.md").render(rows=overview)


def evaluate_csv(csv_fp, output_dp, apikey=None, galaxy_url=DEFAULT_GALAXY_URL):
    """
    Evaluate several histories listed in a CSV file and write one report per history and an overview

    :param csv_fp: path to the CSV file, see `read_students_csv`
    :param output_dp: Path object of the output directory
    :param apikey: optional Galaxy API key
    :param galaxy_url: Galaxy URL used for history ids in the CSV file, the API key is only sent to it
    :return: list of overview rows
    """
    return evaluate_histories(read_students_csv(csv_fp, galaxy_url), output_dp, apikey, galaxy_url)
