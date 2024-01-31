from pathlib import Path

import pytest

from ephemeris._idc_lint import lint_idc_directory
from .test_split_genomes import setup_mock_idc_dir

MISSPELLED_DATA_MANAGER_YAML_STR = """
data_manager_fetch_genome_dbkeys_all_fasta:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/devteam/data_manager_fetch_genome_dbkeys_all_fasta/data_manager_fetch_genome_all_fasta_dbkey/0.0.3'
  tags:
    - fetch_source
data_manager_two_bit_builder:
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

TESTTOOLSHED_DATA_MANAGER_YAML_STR = """
data_manager_fetch_genome_dbkeys_all_fasta:
  tool_id: 'toolshed.g2.bx.psu.edu/repos/devteam/data_manager_fetch_genome_dbkeys_all_fasta/data_manager_fetch_genome_all_fasta_dbkey/0.0.3'
  tags:
    - fetch_source
data_manager_twobit_builder:
  tool_id: 'testtoolshed.g2.bx.psu.edu/repos/devteam/data_manager_twobit_builder/twobit_builder_data_manager/0.0.2'
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


def test_idc_lint_valid(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    lint_idc_directory(tmp_path)


def test_idc_lint_misspelled_dm(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    (tmp_path / "data_managers.yml").write_text(MISSPELLED_DATA_MANAGER_YAML_STR)
    with pytest.raises(Exception) as exc_info:
        lint_idc_directory(tmp_path)
    # misspelled two_bit in data managers so data_manager_twobit_builder is missing
    assert "data_manager_twobit_builder" in str(exc_info.value)

    (tmp_path / "data_managers.yml").write_text(TESTTOOLSHED_DATA_MANAGER_YAML_STR)
    with pytest.raises(Exception) as exc_info:
        lint_idc_directory(tmp_path)
    assert "testtoolshed" in str(exc_info.value)
