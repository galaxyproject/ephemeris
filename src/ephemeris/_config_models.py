from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Union,
)

import yaml
from pydantic import (
    BaseModel,
    Extra,
)

StrOrPath = Union[Path, str]


class RepositoryInstallTarget(BaseModel):
    name: str
    owner: str
    tool_shed_url: Optional[str]
    tool_panel_section_id: Optional[str]
    tool_panel_section_label: Optional[str]
    revisions: Optional[List[str]]
    install_tool_dependencies: Optional[bool]
    install_repository_dependencies: Optional[bool]
    install_resolver_dependencies: Optional[bool]


class RepositoryInstallTargets(BaseModel):
    """ """

    api_key: Optional[str]
    galaxy_instance: Optional[str]
    tools: List[RepositoryInstallTarget]


class DataManager(BaseModel, extra=Extra.forbid):
    tags: List[str]
    tool_id: str


class DataManagers(BaseModel, extra=Extra.forbid):
    __root__: Dict[str, DataManager]


class Genome(BaseModel):
    id: str  # The unique id of the data in Galaxy
    description: str  # The description of the data, including its taxonomy, version and date
    dbkey: Optional[str]
    source: Optional[str]  # The source of the data. Can be: 'ucsc', an NCBI accession number or a URL to a fasta file.

    # The following fields are currently purely for human consumption and unused by
    # IDC infrastructure.
    doi: Optional[str]  # Any DOI associated with the data
    blob: Optional[str]  # A blob for any other pertinent information
    checksum: Optional[str]  # A SHA256 checksum of the original
    version: Optional[str]  # Any version information associated with the data

    # Description of actions (data managers) to run on target genome.
    indexers: Optional[
        List[str]
    ]  # indexers to run - keyed on repository name - see data_managers.yml for how to resolve these to tools
    skiplist: Optional[List[str]]  # unimplemented: but if we implement classes of indexers, these will be ones to skip


class Genomes(BaseModel):
    genomes: List[Genome]


def _read_yaml(path: StrOrPath):
    with open(path) as f:
        return yaml.safe_load(f)


def read_data_managers(path: StrOrPath) -> DataManagers:
    return DataManagers(__root__=_read_yaml(path))


def read_genomes(path: StrOrPath) -> Genomes:
    return Genomes(**_read_yaml(path))


def read_tools(path: StrOrPath) -> RepositoryInstallTargets:
    return RepositoryInstallTargets(**_read_yaml(path))
