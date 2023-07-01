from pathlib import Path

from ephemeris._config_models import read_tools
from ephemeris._idc_data_managers_to_tools import write_shed_install_conf
from .test_split_genomes import setup_mock_idc_dir


def test_idc_lint_valid(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    output_path = tmp_path / "output.yaml"
    write_shed_install_conf(tmp_path / "data_managers.yml", output_path)
    # validate the generated tools file...
    read_tools(output_path)
