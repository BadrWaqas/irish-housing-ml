import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from download_data import extract_csv  # noqa: E402


def _make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_extracts_csv_under_expected_name_whatever_its_member_name(tmp_path):
    zip_path = tmp_path / "PPR-ALL.zip"
    _make_zip(zip_path, {"ppr-all.CSV": b"header\nrow\n"})
    csv_path = tmp_path / "PPR-ALL.csv"

    extract_csv(zip_path, csv_path)

    assert csv_path.read_bytes() == b"header\nrow\n"


def test_rejects_zip_without_a_single_csv(tmp_path):
    zip_path = tmp_path / "PPR-ALL.zip"
    _make_zip(zip_path, {"readme.txt": b"nothing here"})

    with pytest.raises(RuntimeError, match="Expected exactly one CSV"):
        extract_csv(zip_path, tmp_path / "PPR-ALL.csv")
