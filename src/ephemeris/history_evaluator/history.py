"""
Read Galaxy histories without changing anything in Galaxy

A history is first downloaded into a plain dictionary (`load_history`), which can
be saved as JSON, and then turned into a workflow (`build_workflow`) with steps in
the format of a Galaxy workflow file (`.ga`) plus some history information
(outputs, job end time, job cache, history of the job).
"""

import json
import re
from collections import Counter
from urllib import parse

import requests

from ephemeris.history_evaluator.match import tool_key

# fields of the job details kept in a loaded history
JOB_FIELDS = [
    "id",
    "tool_id",
    "tool_version",
    "history_id",
    "user_id",
    "state",
    "create_time",
    "update_time",
    "copied_from_job_id",
    "params",
    "inputs",
    "outputs",
    "output_collections",
]

# fields of the history contents kept in a loaded history
CONTENT_KEYS = "id,uuid,hid,name,extension,file_size,history_content_type,visible,deleted"

# job states of a finished job (a deleted job was cancelled before it finished, the outputs of a
# finished job can still be deleted later: the step is then done, with deleted outputs)
DONE_STATES = ("ok", "skipped")

# one connection for the many API calls of a history
SESSION = requests.Session()

# dataset states of a finished dataset (discarded: see dataset_done)
DATASET_DONE_STATES = ("ok", "deferred", "failed_metadata")


def split_galaxy_url(url):
    """
    Split a link to a Galaxy page into the Galaxy URL and the path of the page

    Galaxy can run under a path (e.g. https://example.org/galaxy), which is kept in the Galaxy URL.

    :param url: link to a history or workflow page
    :return: Galaxy URL and path of the page (e.g. /histories/view)
    """
    parsed = parse.urlparse(url)
    page = re.search(r"/(histories|history|published|u|workflows?)(/|$)", parsed.path)
    # without a known page, the Galaxy URL is the server itself
    root = parsed.path[: page.start()] if page else ""
    return parsed._replace(path=root, params="", query="", fragment="").geturl(), parsed.path.removeprefix(root)


def galaxy_id(value, url):
    """
    Check that an id taken from a link is a Galaxy id (hexadecimal), so that it can not change
    the API path a request is sent to

    :param value: id from the link
    :param url: the link, for the error message
    :return: the id
    :raise ValueError: if it is not a Galaxy id
    """
    if not re.fullmatch(r"[0-9a-f]+", value or ""):
        raise ValueError(f"{url} does not contain a valid Galaxy id")
    return value


def id_from_redirect(url):
    """
    Get the id of a /u/<username>/h/<slug> or /u/<username>/w/<slug> link: Galaxy redirects it to a link with the id

    :param url: link
    :return: id or None
    """
    r = SESSION.get(url, allow_redirects=False, timeout=60)
    location = parse.urlparse(r.headers.get("Location", ""))
    return parse.parse_qs(location.query).get("id", [None])[0]


def get_hist_info(hist_url, apikey=None):
    """
    Get history name and Galaxy URL from history URL

    Supported URLs are the ones with the history id as `id` query parameter
    (e.g. `/histories/view?id=...` or `/published/history?id=...`) and the
    `/u/<username>/h/<slug>` links of published histories.

    :param hist_url: URL to Galaxy history
    :param apikey: optional API key to Galaxy server with history
    :return: Galaxy URL, history name and id
    """
    url = parse.urlparse(hist_url)
    galaxy_url, page_path = split_galaxy_url(hist_url)
    hist_id = parse.parse_qs(url.query).get("id", [None])[0]
    if hist_id is None:
        hist_id = id_from_redirect(hist_url)
    if hist_id is None:
        hist_id = find_history_by_slug(galaxy_url, page_path, apikey)
    if hist_id is None:
        raise ValueError(
            f"Could not open the history {hist_url}. Check that the history is shared with the account of the API key, "
            "or use a link with the history id (e.g. /histories/view?id=...)"
        )
    hist_id = galaxy_id(hist_id, hist_url)
    try:
        hist_name = api_get(galaxy_url, f"histories/{hist_id}", apikey, params={"keys": "name"})["name"]
    except requests.HTTPError as e:
        raise ValueError(
            f"Could not open the history {hist_url} ({e.response.status_code if e.response is not None else e}). "
            "It has to be published, shared via link, or shared with the account of the API key "
            "(the key is only sent to the Galaxy server given with --galaxy_url)"
        ) from e
    return galaxy_url, hist_name, hist_id


def find_history_by_slug(galaxy_url, path, apikey=None):
    """
    Find the id of a history from a /u/<username>/h/<slug> link, among the histories of
    the API key owner and the histories shared with them

    :param galaxy_url: URL of the Galaxy server
    :param path: path of the link
    :param apikey: API key
    :return: history id or None
    """
    parts = [parse.unquote(p) for p in path.strip("/").split("/")]
    if not apikey or len(parts) != 4 or parts[0] != "u" or parts[2] != "h":
        return None
    username, slug = parts[1], parts[3]
    for listing in ("histories/shared_with_me", "histories"):
        try:
            histories = api_get(galaxy_url, listing, apikey, params={"keys": "id,slug,username", "limit": 10000})
        except requests.HTTPError:
            continue
        for history in histories:
            if history.get("slug") == slug and history.get("username") == username:
                return history["id"]
    return None


def api_get(galaxy_url, path, apikey=None, params=None):
    """
    GET request to the Galaxy API

    :param galaxy_url: URL of the Galaxy server
    :param path: path after /api/
    :param apikey: optional API key
    :param params: optional query parameters
    :return: decoded JSON response
    """
    headers = {"x-api-key": apikey} if apikey else {}
    # large histories can take minutes, the limit only stops a stalled server.
    # No redirects: requests would send the API key on to the other host
    r = SESSION.get(
        f"{galaxy_url}/api/{path}", params=params, headers=headers, timeout=(30, 600), allow_redirects=False
    )
    if r.is_redirect:
        raise requests.HTTPError(f"Unexpected redirect from {r.url} to {r.headers.get('Location')}", response=r)
    r.raise_for_status()
    return r.json()


def get_collection_datasets(galaxy_url, hdca_id, apikey=None):
    """
    Get the ids and uuids of all datasets inside a dataset collection, nested collections included,
    and the number of datasets in each state

    :param galaxy_url: URL of the Galaxy server
    :param hdca_id: id of the history dataset collection
    :param apikey: optional API key
    :return: sorted list of dataset ids and uuids, dictionary state -> number of datasets
    """
    ids = set()
    states = Counter()

    def walk(elements):
        for element in elements:
            obj = element.get("object") or {}
            if element.get("element_type") == "dataset_collection":
                walk(obj.get("elements", []))
            else:
                ids.update(v for v in (obj.get("id"), obj.get("uuid")) if v)
                states[obj.get("state")] += 1

    walk(api_get(galaxy_url, f"dataset_collections/{hdca_id}", apikey).get("elements", []))
    return sorted(ids), dict(states)


def load_history(hist_url, apikey=None):
    """
    Download everything needed to rebuild the steps of a history

    :param hist_url: URL to Galaxy history
    :param apikey: API key to Galaxy server with history, optional for published or shared histories
    :return: dictionary with history information, extraction summary, contents, collections (dataset ids
        and states) and jobs
    """
    galaxy_url, hist_name, hist_id = get_hist_info(hist_url, apikey)
    # owner of the history, to tell results copied from the same user from results of someone else
    user_id = api_get(galaxy_url, f"histories/{hist_id}", apikey, params={"keys": "user_id"}).get("user_id")
    summary = api_get(galaxy_url, f"histories/{hist_id}/extraction_summary", apikey)
    contents = api_get(
        galaxy_url,
        f"histories/{hist_id}/contents",
        apikey,
        params={"v": "dev", "keys": CONTENT_KEYS, "limit": 10000},
    )
    collections = {}
    collection_states = {}
    jobs = {}
    for job in summary["jobs"]:
        # jobs and collections that can not be read (e.g. copied from a private history) are skipped
        for output in job["outputs"]:
            if output["history_content_type"] == "dataset_collection" and output["id"] not in collections:
                try:
                    collections[output["id"]], collection_states[output["id"]] = get_collection_datasets(
                        galaxy_url, output["id"], apikey
                    )
                except requests.HTTPError:
                    collections[output["id"]] = []
        if job["step_type"] == "tool" and job.get("id") and job["id"] not in jobs:
            try:
                details = api_get(galaxy_url, f"jobs/{job['id']}", apikey, params={"full": "true"})
            except requests.HTTPError:
                continue
            jobs[job["id"]] = {k: details.get(k) for k in JOB_FIELDS}
    return {
        "galaxy_url": galaxy_url,
        "history_id": hist_id,
        "history_name": hist_name,
        "history_url": hist_url,
        "user_id": user_id,
        "summary": summary,
        "contents": contents,
        "collections": collections,
        "collection_states": collection_states,
        "jobs": jobs,
    }


def group_summary_jobs(summary_jobs):
    """
    Group the extraction summary entries into steps

    Entries of the same mapped over job (same implicit collection jobs id) are merged:
    in copied histories, a mapped over step can be listed once per collection element.
    Entries Galaxy can not turn into a workflow step are skipped.

    :param summary_jobs: list of jobs from the extraction summary
    :return: list of entries, each with the outputs of all merged entries
    """
    steps = []
    by_icj = {}
    for job in summary_jobs:
        if job.get("invalid"):
            continue
        icj = job.get("implicit_collection_jobs_id")
        if icj and icj in by_icj:
            by_icj[icj]["outputs"].extend(job["outputs"])
            continue
        entry = dict(job, outputs=list(job["outputs"]))
        if icj:
            by_icj[icj] = entry
        steps.append(entry)
    return steps


def build_workflow(history):
    """
    Turn a loaded history into a workflow, with steps in the format of a Galaxy workflow file

    Besides the usual keys, tool steps have `job_id`, `history_id` (history where the job ran), `user_id` (user who ran the job),
    `cached` (job result reused from the job cache), `failed` (job failed or not finished, for a step mapped
    over a collection: all its jobs), `failed_elements` and `elements` (datasets of the output collections
    of a mapped over step, failed and all), `end_time`, `inaccessible` (job details can not be read) and all
    steps have `outputs` and `deleted` (all outputs deleted).

    :param history: dictionary from `load_history`
    :return: dictionary with the workflow corresponding to the Galaxy history
    """
    contents = {c["id"]: c for c in history["contents"]}
    steps = {}
    producers = {}  # dataset/collection id or uuid -> index of the step creating it
    for job in group_summary_jobs(history["summary"]["jobs"]):
        index = len(steps)
        outputs = []
        for output in job["outputs"]:
            content = contents.get(output["id"], {})
            outputs.append(
                {
                    "id": output["id"],
                    "hid": output.get("hid"),
                    "name": output.get("name"),
                    "type": output["history_content_type"],
                    "extension": content.get("extension"),
                    "file_size": content.get("file_size"),
                    "deleted": bool(output.get("deleted") or content.get("deleted")),
                }
            )
            producers[output["id"]] = index
            if content.get("uuid"):
                producers[content["uuid"]] = index
            for ds_id in history["collections"].get(output["id"], []):
                producers.setdefault(ds_id, index)
        # a step whose outputs were all deleted is usually an attempt that was thrown away
        deleted = bool(outputs) and all(o["deleted"] for o in outputs)
        if job["step_type"] == "input_dataset":
            steps[str(index)] = {
                "id": index,
                "name": "Input dataset",
                "type": "data_input",
                "tool_id": None,
                "input_connections": {},
                "outputs": outputs,
                "deleted": deleted,
            }
            continue
        if job["step_type"] == "input_collection":
            steps[str(index)] = {
                "id": index,
                "name": "Input dataset collection",
                "type": "data_collection_input",
                "tool_id": None,
                "input_connections": {},
                "outputs": outputs,
                "deleted": deleted,
            }
            continue
        # for mapped over steps, the summary gives one of the jobs
        job_details = history["jobs"].get(job["id"])
        if job_details is None:
            # job not accessible: only the tool and the outputs are known
            steps[str(index)] = {
                "id": index,
                "name": job["tool_name"],
                "type": "tool",
                "tool_id": job["tool_id"],
                "tool_version": job["tool_version"],
                "tool_state": "{}",
                "input_connections": {},
                "outputs": outputs,
                "deleted": deleted,
                "job_id": job["id"],
                "history_id": None,
                "user_id": None,
                "inaccessible": True,
                "cached": False,
                "failed": False,
                "failed_elements": 0,
                "elements": 0,
                "end_time": None,
            }
            continue
        # a mapped over step has one job per collection element, the summary gives one of them:
        # the states of the output datasets tell how many failed. Each output collection has the
        # datasets of all jobs, so the collection with the most failed datasets is counted.
        elements, failed_elements = 0, 0
        if job.get("implicit_collection_jobs_id"):
            for output in job["outputs"]:
                states = history.get("collection_states", {}).get(output["id"], {})
                failed = sum(n for state, n in states.items() if not dataset_done(state, job_details))
                if (failed, sum(states.values())) > (failed_elements, elements):
                    failed_elements, elements = failed, sum(states.values())
        parameters = dict(job_details["params"])
        input_connections = {}
        for name, inp in job_details["inputs"].items():
            producer = producers.get(inp.get("id"), producers.get(inp.get("uuid")))
            input_connections[name] = {} if producer is None else {"id": producer, "output_name": "output"}
        steps[str(index)] = {
            "id": index,
            "name": job["tool_name"],
            "type": "tool",
            "tool_id": job["tool_id"],
            "tool_version": job["tool_version"],
            "tool_state": json.dumps(parameters),
            "input_connections": input_connections,
            "outputs": outputs,
            "deleted": deleted,
            "job_id": job["id"],
            "history_id": job_details["history_id"],
            "user_id": job_details.get("user_id"),
            "cached": bool(job_details.get("copied_from_job_id")),
            "failed": failed_elements == elements if elements else not job_finished(job_details),
            "failed_elements": failed_elements,
            "elements": elements,
            "end_time": job_details.get("update_time"),
        }
    return {
        "a_galaxy_workflow": "true",
        "name": f"{history['history_name']} workflow",
        "history_id": history["history_id"],
        "main_history_id": get_main_history_id(history["history_id"], steps),
        "user_id": history.get("user_id"),
        "galaxy_url": history["galaxy_url"],
        "steps": steps,
    }


def job_finished(job_details):
    """
    Check if a job finished (interactive tools end as deleted, or stopped since Galaxy 26.2, when they are stopped)

    :param job_details: job details
    :return: boolean
    """
    if tool_key(job_details.get("tool_id")).startswith("interactive_tool_"):
        return job_details.get("state") in DONE_STATES + ("deleted", "deleting", "stopped", "stopping")
    return job_details.get("state") in DONE_STATES


def dataset_done(state, job_details):
    """
    Check if an output dataset is finished. Discarded datasets have no data: the outputs of a cancelled
    job (not finished), or of a finished job whose data was purged or not imported (finished).

    :param state: dataset state
    :param job_details: details of the job (one of the jobs, for a mapped over step)
    :return: boolean
    """
    return state in DATASET_DONE_STATES or (state == "discarded" and job_finished(job_details))


def get_main_history_id(hist_id, steps):
    """
    Find the history where the analysis was run

    It is the history itself if at least one job ran in it, otherwise (e.g. for an imported
    copy of a history) the history where most jobs ran.

    :param hist_id: id of the history
    :param steps: workflow steps of the history
    :return: history id
    """
    job_histories = Counter(s["history_id"] for s in steps.values() if s.get("history_id"))
    if not job_histories or hist_id in job_histories:
        return hist_id
    return job_histories.most_common(1)[0][0]


def get_workflow_from_history(hist_url, apikey=None):
    """
    Build a workflow from a Galaxy history, without changing anything in Galaxy

    The steps come from the history extraction summary (the jobs and inputs Galaxy
    would use to extract a workflow) and the connections from the inputs of the jobs.

    :param hist_url: URL to Galaxy history
    :param apikey: API key to Galaxy server with history, optional for published or shared histories
    :return: dictionary with the workflow corresponding to Galaxy history
    """
    return build_workflow(load_history(hist_url, apikey))


def fetch_dataset_text(galaxy_url, dataset_id, apikey=None, max_bytes=200000):
    """
    Get the beginning of a dataset content as text

    :param galaxy_url: URL of the Galaxy server
    :param dataset_id: id of the dataset
    :param apikey: optional API key
    :param max_bytes: maximum number of bytes to read
    :return: text or None if the dataset can not be read or is not text
    """
    headers = {"x-api-key": apikey} if apikey else {}
    try:
        with SESSION.get(
            f"{galaxy_url}/api/datasets/{dataset_id}/display",
            headers=headers,
            stream=True,
            timeout=60,
            allow_redirects=not apikey,
        ) as r:
            r.raise_for_status()
            if r.is_redirect:
                return None
            data = r.raw.read(max_bytes, decode_content=True)
    except requests.RequestException:
        return None
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")
