from pathlib import Path

from ephemeris._idc_lint import lint_idc_directory
from .test_split_genomes import setup_mock_idc_dir


def test_idc_lint(tmp_path: Path):
    setup_mock_idc_dir(tmp_path)
    lint_idc_directory(tmp_path)
