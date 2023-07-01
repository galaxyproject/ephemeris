from pathlib import Path

import yaml

from ephemeris._idc_split_data_manager_genomes import (
    GalaxyHistoryIsBuildComplete,
    RunDataManagers,
    split_genomes,
    SplitOptions,
)

MERGED_YAML_STR = """
genomes:
    - dbkey: hg19_rCRS_pUC18_phiX174
      description: Homo sapiens (hg19 with mtDNA replaced with rCRS, and containing pUC18
        and phiX174)
      source: http://datacache.galaxyproject.org/managed/seq/hg19_rCRS_pUC18_phiX174.fa
      id: hg19_rCRS_pUC18_phiX174
      indexers:
      - data_manager_twobit_builder
      - data_manager_star_index_builder

    - dbkey: rn6
      description: Rat Jul. 2014 (RGSC 6.0/rn6) (rn6)
      id: rn6
      source: ucsc
      indexers:
      - data_manager_twobit_builder
      - data_manager_picard_index_builder
"""

DATA_MANAGER_YAML_STR = """
data_manager_fetch_genome_dbkeys_all_fasta:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/devteam/data_manager_fetch_genome_dbkeys_all_fasta/data_manager_fetch_genome_all_fasta_dbkey/0.0.3'
  tags:
    - fetch_source
data_manager_twobit_builder:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/devteam/data_manager_twobit_builder/twobit_builder_data_manager/0.0.2'
  tags:
  - genome
data_manager_picard_index_builder:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/devteam/data_manager_picard_index_builder/data_manager/picard_index_builder/0.0.1'
  tags:
  - genome
data_manager_star_index_builder:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/iuc/data_manager_star_index_builder/rna_star_index_builder_data_manager/0.0.5'
  tags:
  - genome
"""


def setup_mock_idc_dir(directory: Path):
    merged = directory / "genomes.yml"
    merged.write_text(MERGED_YAML_STR)

    data_managers = directory / "data_managers.yml"
    data_managers.write_text(DATA_MANAGER_YAML_STR)


def read_and_validate_run_data_manager_yaml(path):
    with open(path, "r") as f:
        return RunDataManagers(**yaml.safe_load(f))


def test_split_genomes(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)

    split_path = tmp_path / "split"

    history_names = ["idc-hg19_rCRS_pUC18_phiX174-data_manager_star_index_builder"]
    is_build_complete = GalaxyHistoryIsBuildComplete(history_names)

    split_options = SplitOptions()
    split_options.merged_genomes_path = tmp_path / "genomes.yml"
    split_options.split_genomes_path = str(split_path)
    split_options.data_managers_path = tmp_path / "data_managers.yml"
    split_options.is_build_complete = is_build_complete
    split_genomes(split_options)
    new_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    complete_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_star_index_builder"
    assert new_task.exists()
    assert not complete_task.exists()
    new_task_run_yaml = new_task / "run_data_managers.yaml"
    # ensure we don't serialize unset fields
    assert "data_table_reload" not in new_task_run_yaml.read_text()
    run = read_and_validate_run_data_manager_yaml(new_task_run_yaml)
    assert len(run.data_managers) == 1
    data_manager = run.data_managers[0]
    assert data_manager.id == "toolshed.g2.bx.psu.edu/repos/devteam/data_manager_twobit_builder/twobit_builder_data_manager/0.0.2"
    assert data_manager.items[0]["id"] == "hg19_rCRS_pUC18_phiX174"
    assert data_manager.items[0]["dbkey"] == "hg19_rCRS_pUC18_phiX174"
