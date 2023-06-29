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
    read_data_managers(data_managers_path)
    read_genomes(genomes_path)


def main():
    lint_idc_directory(Path(os.curdir))


if __name__ == "__main__":
    main()
