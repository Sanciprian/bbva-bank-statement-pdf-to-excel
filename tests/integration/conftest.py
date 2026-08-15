from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "input"


def _real_pdfs() -> list[Path]:
    if not INPUT_DIR.is_dir():
        return []
    return sorted(INPUT_DIR.glob("*.pdf"))


@pytest.fixture(scope="session")
def real_pdfs() -> list[Path]:
    pdfs = _real_pdfs()
    if not pdfs:
        pytest.skip("no PDFs in input/ -- integration suite is a no-op on a fresh clone")
    return pdfs
