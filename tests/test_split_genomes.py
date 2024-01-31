from pathlib import Path

import yaml

from ephemeris._idc_split_data_manager_genomes import (
    Filters,
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
    with open(path) as f:
        return RunDataManagers(**yaml.safe_load(f))


def split_options_for(tmp_path: Path) -> SplitOptions:
    history_names = ["idc-hg19_rCRS_pUC18_phiX174-data_manager_star_index_builder"]
    is_build_complete = GalaxyHistoryIsBuildComplete(history_names)

    split_options = SplitOptions()
    split_options.merged_genomes_path = tmp_path / "genomes.yml"
    split_options.split_genomes_path = str(tmp_path / "split")
    split_options.data_managers_path = tmp_path / "data_managers.yml"
    split_options.is_build_complete = is_build_complete
    return split_options


def test_split_genomes(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
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
    assert (
        data_manager.id
        == "toolshed.g2.bx.psu.edu/repos/devteam/data_manager_twobit_builder/twobit_builder_data_manager/0.0.2"
    )
    assert data_manager.items[0]["id"] == "hg19_rCRS_pUC18_phiX174"
    assert data_manager.items[0]["dbkey"] == "hg19_rCRS_pUC18_phiX174"


def test_split_genomes_short_ids(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
    split_options.tool_id_mode = "short"
    split_genomes(split_options)

    new_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    new_task_run_yaml = new_task / "run_data_managers.yaml"
    run = read_and_validate_run_data_manager_yaml(new_task_run_yaml)
    assert len(run.data_managers) == 1
    data_manager = run.data_managers[0]
    assert data_manager.id == "twobit_builder_data_manager"


def test_split_genomes_filter_on_data_manager(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
    filters = Filters()
    filters.data_manager = "data_manager_star_index_builder"
    split_options.filters = filters

    split_genomes(split_options)
    new_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    assert not new_task.exists()

    filters.data_manager = "data_manager_twobit_builder"
    split_genomes(split_options)
    assert new_task.exists()


def test_split_genomes_filter_on_build_id(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
    filters = Filters()
    filters.build_id = "rn6"
    split_options.filters = filters

    split_genomes(split_options)
    filtered_out_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    assert not filtered_out_task.exists()

    filtered_in_task = split_path / "rn6" / "data_manager_twobit_builder"
    assert filtered_in_task.exists()


def test_split_genomes_filter_on_stage_0(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
    filters = Filters()
    filters.stage = 0
    split_options.filters = filters

    split_genomes(split_options)
    filtered_out_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    assert not filtered_out_task.exists()

    filtered_in_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_fetch_genome_dbkeys_all_fasta"
    assert filtered_in_task.exists()


def test_split_genomes_filter_on_stage_1(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    split_path = tmp_path / "split"
    split_options = split_options_for(tmp_path)
    filters = Filters()
    filters.stage = 1
    split_options.filters = filters

    split_genomes(split_options)
    filtered_out_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_fetch_genome_dbkeys_all_fasta"
    assert not filtered_out_task.exists()

    filtered_in_task = split_path / "hg19_rCRS_pUC18_phiX174" / "data_manager_twobit_builder"
    assert filtered_in_task.exists()
