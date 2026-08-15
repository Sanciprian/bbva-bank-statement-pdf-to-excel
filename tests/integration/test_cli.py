from pathlib import Path

from bank_parser.cli import main

_INPUT_DIR = Path(__file__).resolve().parents[2] / "input"


def test_cli_end_to_end_against_real_input(real_pdfs, tmp_path):
    output_dir = tmp_path / "output"

    exit_code = main(["--input", str(_INPUT_DIR), "--output-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "transacciones.csv").exists()
    assert (output_dir / "transacciones.xlsx").exists()


def test_cli_reports_missing_input_dir(tmp_path):
    empty_input = tmp_path / "no_pdfs_here"
    empty_input.mkdir()

    exit_code = main(["--input", str(empty_input), "--output-dir", str(tmp_path / "output")])

    assert exit_code == 1
