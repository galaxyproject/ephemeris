"""
Match the steps of a history to the steps of a reference (workflow or history)

Steps are matched by tool and by where their inputs come from, not by their order,
so reruns, extra steps and steps run in another order are handled.
"""

import json
from difflib import SequenceMatcher

INPUT_TYPES = ("data_input", "data_collection_input", "parameter_input")

# parameters depending on the Galaxy server or the run, not on the analysis
IGNORED_PARAMETERS = [
    "__page__",
    "__input_ext",
    "chromInfo",
    "__rerun_remap_job_id__",
    "dbkey",
    "__job_resource",
    "__workflow_invocation_uuid__",
    "__use_cached_job__",
]

# value of a data input: compared as a connection, not as a setting
CONNECTED = object()


def is_data_value(value):
    """
    Check if a parameter value is a data input: a connection in a workflow file, datasets in a job

    :param value: decoded parameter value
    :return: boolean
    """
    if value.get("__class__") == "ConnectedValue" or value.get("src") in ("hda", "hdca", "ldda", "dce"):
        return True
    values = value.get("values")
    return (
        set(value) == {"values"}
        and isinstance(values, list)
        and all(isinstance(v, dict) and "src" in v for v in values)
    )


def is_ignored(name, nested=False):
    """
    Check if a parameter is ignored: internal parameters and element names of collections

    :param name: parameter name
    :param nested: True for a parameter inside a conditional, section or repeat
    :return: boolean
    """
    if name.endswith("__identifier__"):
        return True
    return name == "__current_case__" if nested else name in IGNORED_PARAMETERS


def is_input_step(step):
    """
    Check if a workflow step is an input step

    :param step: dictionary with a workflow step
    :return: boolean
    """
    return step["name"] in ("Input dataset", "Data Fetch") or step["type"] in INPUT_TYPES


def tool_key(tool_id):
    """
    Get the part of a tool id that does not depend on the tool version or ToolShed

    :param tool_id: full tool id, e.g. toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.73+galaxy0
    :return: short tool id, e.g. fastqc
    """
    parts = str(tool_id).split("/")
    if len(parts) >= 6 and parts[1] == "repos":
        return parts[4]
    return str(tool_id)


def normalize_value(value):
    """
    Turn a parameter value into a comparable value

    Workflow files and jobs store values differently (e.g. `7`, `"7"` or `"\\"7\\""`,
    data inputs as `{"__class__": "ConnectedValue"}` or `{"values": [{"id": ..., "src": "hda"}]}`),
    so JSON strings are decoded, data inputs become `CONNECTED` and are left out of dictionaries
    and lists, runtime values become None and scalars become strings.

    :param value: parameter value
    :return: normalized value
    """
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            decoded = json.loads(value)
        except ValueError:
            break
        if decoded == value:
            break
        value = decoded
    if isinstance(value, dict):
        if is_data_value(value):
            return CONNECTED
        if value.get("__class__") == "RuntimeValue":
            return None
        return without_data({k: normalize_value(v) for k, v in value.items() if not is_ignored(k, nested=True)})
    if isinstance(value, list):
        return [v for v in map(normalize_value, value) if v is not CONNECTED]
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def clean_parameters(tool_state):
    """
    Turn the tool state of a workflow step into comparable parameters

    :param tool_state: JSON string with the tool state
    :return: dictionary with parameters
    """
    parameters = json.loads(tool_state) if isinstance(tool_state, str) else dict(tool_state or {})
    return without_data({p: normalize_value(v) for p, v in parameters.items() if not is_ignored(p)})


def without_data(parameters):
    """
    Remove the data inputs from normalized parameters

    :param parameters: dictionary with normalized values
    :return: dictionary
    """
    return {p: v for p, v in parameters.items() if v is not CONNECTED}


def step_parameters(step):
    """
    Get the comparable parameters of a workflow step, without the connected data inputs
    (older workflow files store them as null)

    :param step: workflow step
    :return: dictionary with parameters
    """
    connected = set(step.get("input_connections", {}))
    return {p: v for p, v in clean_parameters(step.get("tool_state", "{}")).items() if p not in connected}


def parameter_agreement(ref_step, hist_step):
    """
    Fraction of the reference step parameters with the same value in the history step

    :param ref_step: workflow step of the reference
    :param hist_step: workflow step of the history
    :return: number between 0 and 1
    """
    ref_params = step_parameters(ref_step)
    hist_params = step_parameters(hist_step)
    if not ref_params:
        return 1.0
    same = sum(1 for p, v in ref_params.items() if hist_params.get(p) == v)
    return same / len(ref_params)


def connection_ids(step):
    """
    Get the indexes of the steps connected to the inputs of a step

    :param step: workflow step
    :return: list of step indexes
    """
    ids = []
    for connection in step.get("input_connections", {}).values():
        for c in connection if isinstance(connection, list) else [connection]:
            if isinstance(c, dict) and "id" in c:
                ids.append(int(c["id"]))
    return ids


def connections_by_name(step):
    """
    Get the indexes of the steps connected to each input of a step

    Jobs name the datasets of a multiple input `name`, `name1`, `name2`, ... (e.g. `inputs`,
    `inputs1`, or `opt_in1`, `opt_in11`): they are merged into the input. Numbers that do not
    follow on from 1 are other inputs (e.g. `input` and `input2`).

    :param step: workflow step
    :return: dictionary input name -> list of step indexes
    """
    names = step.get("input_connections", {})
    merged = {}
    for base in sorted(names, key=len):
        if base in merged:
            continue
        numbered = {
            int(n.removeprefix(base)): n
            for n in names
            if n not in merged
            and n != base
            and n.startswith(base)
            and n.removeprefix(base).isdigit()
            and not n.removeprefix(base).startswith("0")
        }
        if numbered and sorted(numbered) == list(range(1, len(numbered) + 1)):
            merged.update({n: base for n in numbered.values()})
    by_name = {}
    for name, connection in names.items():
        for c in connection if isinstance(connection, list) else [connection]:
            if isinstance(c, dict) and "id" in c:
                by_name.setdefault(merged.get(name, name), []).append(int(c["id"]))
    return by_name


def same_format(ref_input, hist_input):
    """
    Check if two input steps can be the same data: same datatype, if both are known
    (a workflow file does not have the datatype of its inputs)

    :param ref_input: input step of the reference
    :param hist_input: input step of the history
    :return: boolean
    """
    formats = [(s.get("outputs") or [{}])[0].get("extension") for s in (ref_input, hist_input)]
    return None in formats or formats[0] == formats[1]


def sorted_indexes(steps, inputs):
    """
    Get the indexes of input or tool steps, in step order

    :param steps: workflow steps (dictionary)
    :param inputs: True for input steps, False for tool steps
    :return: sorted list of indexes
    """
    return sorted(int(k) for k, s in steps.items() if is_input_step(s) == inputs)


def thrown_away(steps):
    """
    Get the tool steps that were thrown away: failed, or attempts replaced by another run, i.e. with
    all outputs deleted, not used by a kept step (a deleted output used later, e.g. to save space, is
    still a real step) and with a kept run of the same tool (a deleted final result is still a result)

    :param steps: workflow steps (dictionary)
    :return: set of step indexes
    """
    steps = {int(k): s for k, s in steps.items()}
    away = {i for i, s in steps.items() if not is_input_step(s) and (s.get("failed") or s.get("deleted"))}
    changed = True
    while changed:
        changed = False
        kept = [i for i in steps if i not in away]
        used = {p for i in kept for p in connection_ids(steps[i])}
        kept_tools = {tool_key(steps[i]["tool_id"]) for i in kept if not is_input_step(steps[i])}
        for i in list(away):
            if not steps[i].get("failed") and (i in used or tool_key(steps[i]["tool_id"]) not in kept_tools):
                away.discard(i)
                changed = True
    return away


def match_steps(ref_steps, hist_steps):
    """
    Match the steps of a history to the steps of a reference

    Reference tool steps are taken in order, the ones thrown away (see `thrown_away`) last. A history
    step can match a reference step if it uses the same tool and did not fail; thrown away reference
    steps only match thrown away history steps. Among them, the preferred one has the most inputs
    coming from steps already matched to the inputs of the reference step, then thrown away or not
    like the reference step, then the most similar parameters, then outputs used by other steps,
    then the same tool version, then the same position among the runs of the tool (e.g. the 2nd run
    with the 2nd run), then the latest end time.
    Input steps are matched after the tool steps: each matched tool step votes for the history input
    it used where the reference used an input (on the same input of the tool if possible), the input
    with the most votes wins, then the same datatype, then the same position among the inputs. So one
    step run on the wrong input does not change which input is which. The others are matched by order.

    :param ref_steps: steps of the reference workflow (dictionary)
    :param hist_steps: steps of the history workflow (dictionary)
    :return: dictionary with `mapping` (reference index -> history index), `missing` and `extra` tool step indexes
    """
    ref = {int(k): s for k, s in ref_steps.items()}
    hist = {int(k): s for k, s in hist_steps.items()}
    consumed = {i for s in hist.values() for i in connection_ids(s)}

    def occurrences(steps):
        # position of each tool step among the steps with the same tool
        seen, occ = {}, {}
        for i in sorted_indexes(steps, inputs=False):
            key = tool_key(steps[str(i)]["tool_id"])
            occ[i] = seen.get(key, 0)
            seen[key] = occ[i] + 1
        return occ

    ref_occ, hist_occ = occurrences(ref_steps), occurrences(hist_steps)
    ref_away, hist_away = thrown_away(ref_steps), thrown_away(hist_steps)
    mapping = {}
    used = set()
    for r in sorted(sorted_indexes(ref_steps, inputs=False), key=lambda r: (r in ref_away, r)):
        # ignore connections to steps that are not there (e.g. deleted)
        r_prod = [p for p in connection_ids(ref[r]) if p in ref]
        best, best_key = None, None
        for h in sorted_indexes(hist_steps, inputs=False):
            if h in used or tool_key(hist[h]["tool_id"]) != tool_key(ref[r]["tool_id"]):
                continue
            # a failed run is not done, a thrown away attempt of the reference is not the real step
            if (r in ref_away and h not in hist_away) or (hist[h].get("failed") and r not in ref_away):
                continue
            h_prod = [q for q in connection_ids(hist[h]) if q in hist]
            free_inputs = [q for q in h_prod if is_input_step(hist[q]) and q not in used]
            connected = sum(
                1
                for p in r_prod
                if (p in mapping and mapping[p] in h_prod)
                or (p not in mapping and is_input_step(ref[p]) and free_inputs)
            )
            key = (
                connected,
                (h in hist_away) == (r in ref_away),
                parameter_agreement(ref[r], hist[h]),
                h in consumed,
                hist[h].get("tool_id") == ref[r].get("tool_id"),
                -abs(hist_occ[h] - ref_occ[r]),
                hist[h].get("end_time") or "",
            )
            if best_key is None or key > best_key:
                best, best_key = h, key
        if best is None:
            continue
        mapping[r] = best
        used.add(best)
    # inputs: votes of the matched tool steps
    ref_inputs, hist_inputs = sorted_indexes(ref_steps, inputs=True), sorted_indexes(hist_steps, inputs=True)
    votes = {}
    for r, h in list(mapping.items()):
        hist_by_name = connections_by_name(hist[h])
        for name, r_ids in connections_by_name(ref[r]).items():
            candidates = [
                q for q in hist_by_name.get(name, connection_ids(hist[h])) if q in hist and is_input_step(hist[q])
            ]
            for p in r_ids:
                if p in ref and is_input_step(ref[p]):
                    for q in candidates:
                        if hist[q]["type"] == ref[p]["type"]:
                            votes[(p, q)] = votes.get((p, q), 0) + 1
    for (p, q), _ in sorted(
        votes.items(),
        key=lambda pv: (
            -pv[1],
            not same_format(ref[pv[0][0]], hist[pv[0][1]]),
            abs(ref_inputs.index(pv[0][0]) - hist_inputs.index(pv[0][1])),
        ),
    ):
        if p not in mapping and q not in used:
            mapping[p] = q
            used.add(q)
    # remaining inputs by order, of the same datatype if possible
    free = [q for q in hist_inputs if q not in used]
    for p in sorted_indexes(ref_steps, inputs=True):
        if p in mapping:
            continue
        candidates = [q for q in free if hist[q]["type"] == ref[p]["type"]]
        q = next((q for q in candidates if same_format(ref[p], hist[q])), candidates[0] if candidates else None)
        if q is not None:
            mapping[p] = q
            used.add(q)
            free.remove(q)
    return {
        "mapping": mapping,
        "thrown_away": sorted(ref_away),
        "hist_thrown_away": sorted(hist_away),
        "missing": [r for r in sorted_indexes(ref_steps, inputs=False) if r not in mapping and r not in ref_away],
        "extra": [h for h in sorted_indexes(hist_steps, inputs=False) if h not in used],
    }


def same_connections(ref_step, hist_step, mapping):
    """
    Check if the inputs of matched steps come from matched steps, input by input
    (e.g. swapped inputs of an intersect are not the same)

    :param ref_step: reference workflow step
    :param hist_step: history workflow step
    :param mapping: reference index -> history index
    :return: boolean
    """
    if {mapping.get(p) for p in connection_ids(ref_step)} != set(connection_ids(hist_step)):
        return False
    hist_by_name = connections_by_name(hist_step)
    return all(
        {mapping.get(p) for p in ids} == set(hist_by_name[name])
        for name, ids in connections_by_name(ref_step).items()
        if name in hist_by_name
    )


def text_similarity(text1, text2):
    """
    Similarity of two texts, line by line

    :param text1: first text
    :param text2: second text
    :return: number between 0 and 1
    """
    if text1 == text2:
        return 1.0
    lines1 = text1.splitlines()[:5000]
    lines2 = text2.splitlines()[:5000]
    if not lines1 or not lines2:
        return 0.0
    return SequenceMatcher(None, lines1, lines2, autojunk=False).ratio()
