import os
from pathlib import Path

import yaml

from ._config_models import (
    read_data_managers,
    read_genomes,
)


def read_yaml(path: Path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def lint_idc_directory(directory: Path):
    genomes_path = directory / "genomes.yml"
    data_managers_path = directory / "data_managers.yml"
    assert genomes_path.exists()
    assert data_managers_path.exists()
    data_managers = read_data_managers(data_managers_path).__root__
    genomes = read_genomes(genomes_path)
    print(genomes)
    for genome in genomes.genomes:
        print(genome)
        for indexer in (genome.indexers or []):
            if indexer not in data_managers:
                raise Exception(f"Failed to find data manager {indexer} referenced for genome {genome}")


def main():
    lint_idc_directory(Path(os.curdir))


if __name__ == "__main__":
    main()
