from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    Extra,
    RootModel,
)

StrOrPath = Path | str


class RepositoryInstallTarget(BaseModel):
    name: str
    owner: str
    tool_shed_url: str | None = None
    tool_panel_section_id: str | None = None
    tool_panel_section_label: str | None = None
    revisions: list[str] | None = None
    install_tool_dependencies: bool | None = None
    install_repository_dependencies: bool | None = None
    install_resolver_dependencies: bool | None = None


class RepositoryInstallTargets(BaseModel):
    """ """

    api_key: str | None = None
    galaxy_instance: str | None = None
    tools: list[RepositoryInstallTarget]


class DataManager(BaseModel, extra=Extra.forbid):
    tags: list[str]
    tool_id: str


class DataManagers(RootModel):
    root: dict[str, DataManager]


class Genome(BaseModel):
    id: str  # The unique id of the data in Galaxy
    description: str | None = None  # The description of the data, including its taxonomy, version and date
    dbkey: str | None = None
    source: str | None = (
        None  # The source of the data. Can be: 'ucsc', an NCBI accession number or a URL to a fasta file.
    )

    # The following fields are currently purely for human consumption and unused by
    # IDC infrastructure.
    doi: str | None = None  # Any DOI associated with the data
    blob: str | None = None  # A blob for any other pertinent information
    checksum: str | None = None  # A SHA256 checksum of the original
    version: str | None = None  # Any version information associated with the data

    # Description of actions (data managers) to run on target genome.
    indexers: (
        list[str] | None
    )  # indexers to run - keyed on repository name - see data_managers.yml for how to resolve these to tools
    skiplist: list[str] | None = (
        None  # unimplemented: but if we implement classes of indexers, these will be ones to skip
    )


class Genomes(BaseModel):
    genomes: list[Genome]


def _read_yaml(path: StrOrPath):
    with open(path) as f:
        return yaml.safe_load(f)


def read_data_managers(path: StrOrPath) -> DataManagers:
    return DataManagers(root=_read_yaml(path))


def read_genomes(path: StrOrPath) -> Genomes:
    return Genomes(**_read_yaml(path))


def read_tools(path: StrOrPath) -> RepositoryInstallTargets:
    return RepositoryInstallTargets(**_read_yaml(path))
