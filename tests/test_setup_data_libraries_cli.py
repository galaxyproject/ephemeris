import io
import pathlib

import pytest

import ephemeris.setup_data_libraries as setup_data_libraries
from ephemeris.setup_data_libraries import main as setup_data_libraries_cli
from .conftest import GalaxyContainer

LIBRARY_DATA_EXAMPLE = pathlib.Path(__file__).parent / "library_data_example.yaml"


class MockTools:
    def __init__(self):
        self.posts = []

    def _post(self, payload=None, id=None):
        self.posts.append({"payload": payload, "id": id})
        return {"jobs": [{"id": "job-id"}]}


class MockGalaxyInstance:
    def __init__(self):
        self.url = "https://example.org/api"
        self.tools = MockTools()


def test_fetch_upload_preserves_metadata_and_uses_library_folder_destination():
    gi = MockGalaxyInstance()

    result = setup_data_libraries._fetch_upload(
        gi,
        "history-id",
        "Ffolder-id",
        [
            {
                "url": "https://example.org/data/genome.fa",
                "name": "human genome",
                "ext": "fasta",
                "info": "reference data",
                "dbkey": "hg38",
                "sha256": "abc123",
            }
        ],
        deferred=True,
    )

    assert result == {"jobs": [{"id": "job-id"}]}
    assert gi.tools.posts == [
        {
            "id": "fetch",
            "payload": {
                "history_id": "history-id",
                "targets": [
                    {
                        "destination": {
                            "type": "library_folder",
                            "library_folder_id": "folder-id",
                        },
                        "elements": [
                            {
                                "src": "url",
                                "url": "https://example.org/data/genome.fa",
                                "name": "human genome",
                                "ext": "fasta",
                                "info": "reference data",
                                "dbkey": "hg38",
                                "deferred": True,
                                "SHA-256": "abc123",
                            }
                        ],
                    }
                ],
            },
        }
    ]


def test_fetch_upload_rejects_non_url_sources():
    gi = MockGalaxyInstance()

    with pytest.raises(Exception, match="Only URL source items are supported"):
        setup_data_libraries._fetch_upload(
            gi,
            "history-id",
            "folder-id",
            [{"src": "files", "url": "/tmp/genome.fa"}],
        )


def test_hash_fields_normalizes_supported_hash_keys():
    assert setup_data_libraries._hash_fields(
        {
            "MD5": "md5-value",
            "sha1": "sha1-value",
            "SHA-256": "sha256-value",
            "sha512": "sha512-value",
        }
    ) == {
        "MD5": "md5-value",
        "SHA-1": "sha1-value",
        "SHA-256": "sha256-value",
        "SHA-512": "sha512-value",
    }


def test_setup_data_libraries_waits_for_fetch_jobs(monkeypatch):
    states = ["running", "ok"]
    sleeps = []

    class MockJobsClient:
        def __init__(self, gi):
            self.gi = gi

        def get_state(self, job_id):
            assert job_id == "job-id"
            return states.pop(0)

    def mock_create_library(gi, library_def, make_public=False, deferred=False):
        assert library_def["items"][0]["ext"] == "fasta"
        assert make_public is True
        assert deferred is True
        return [{"jobs": [{"id": "job-id"}]}]

    monkeypatch.setattr(setup_data_libraries, "create_library", mock_create_library)
    monkeypatch.setattr(setup_data_libraries.galaxy.jobs, "JobsClient", MockJobsClient)
    monkeypatch.setattr(setup_data_libraries, "DEFAULT_JOB_SLEEP", 0)
    monkeypatch.setattr(setup_data_libraries.time, "sleep", sleeps.append)

    setup_data_libraries.setup_data_libraries(
        object(),
        io.StringIO(
            """
destination:
  type: library
items:
  - url: https://example.org/data/genome.fa
    file_type: fasta
"""
        ),
        make_public=True,
        deferred=True,
    )

    assert sleeps == [0]
    assert states == []


def test_parser_accepts_deprecated_legacy_flag():
    args = setup_data_libraries._parser().parse_args(
        [
            "-a",
            "api-key",
            "-g",
            "https://example.org",
            "-i",
            str(LIBRARY_DATA_EXAMPLE),
            "--legacy",
        ]
    )

    assert args.legacy is True


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
