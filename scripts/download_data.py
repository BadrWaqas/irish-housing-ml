"""
Downloads the full Property Price Register (PPR) from propertypriceregister.ie
into data/raw/PPR-ALL.csv.

The PPR is Ireland's official record of residential property sale prices,
published by the Property Services Regulatory Authority (PSRA) — every
residential sale in the country since 1 January 2010, self-reported by
buyers' solicitors. It's genuinely large (roughly 800,000 rows and growing
every week) and the site itself only offers a slow, paginated search UI —
but it also publishes one bulk "download all" ZIP, which is what this
script grabs.

Why a separate download script instead of just committing the CSV to the
repo? Two reasons:
1. Size — the raw file is over 100MB uncompressed, which is a bad fit for
   git (git isn't built to diff or version large binary-ish blobs, and
   GitHub itself will warn or reject files that large).
2. It goes stale. The register grows every week, so "the CSV in the repo"
   would be a snapshot frozen the day someone committed it. A script that
   re-downloads the current file means every run of this pipeline analyzes
   today's register, not this-project's-birthday's register.

Usage:
    python scripts/download_data.py
"""

import shutil
import zipfile
from pathlib import Path

import requests

PPR_ZIP_URL = (
    "https://www.propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/"
    "Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
ZIP_PATH = RAW_DIR / "PPR-ALL.zip"
CSV_PATH = RAW_DIR / "PPR-ALL.csv"


def extract_csv(zip_path: Path, csv_path: Path) -> None:
    """Extract the single CSV inside the PPR zip to csv_path.

    Rather than trusting the member name inside the zip to be exactly
    "PPR-ALL.csv" (a rename on the PSRA side would otherwise surface later as
    a confusing "file not found" in load_to_sqlite.py), we pick the one .csv
    member and write it to the path the rest of the pipeline expects.
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise RuntimeError(
                f"Expected exactly one CSV in {zip_path.name}, found {csv_members or 'none'}"
            )
        with zf.open(csv_members[0]) as src, open(csv_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {PPR_ZIP_URL} ...")
    # A plain requests default User-Agent gets blocked by this server;
    # pretending to be an ordinary browser is enough to get through.
    # Write to a .part file first so an interrupted download never leaves a
    # truncated PPR-ALL.zip that looks complete on the next run.
    part_path = ZIP_PATH.with_suffix(".zip.part")
    with requests.get(
        PPR_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True
    ) as response:
        response.raise_for_status()
        with open(part_path, "wb") as f:
            for block in response.iter_content(chunk_size=1 << 20):
                f.write(block)
    part_path.replace(ZIP_PATH)
    print(f"Saved {ZIP_PATH.stat().st_size:,} bytes -> {ZIP_PATH}")

    extract_csv(ZIP_PATH, CSV_PATH)
    print(f"Extracted -> {CSV_PATH}")

    with open(CSV_PATH, encoding="cp1252", errors="replace") as f:
        line_count = sum(1 for _ in f)
    print(f"{line_count - 1:,} sale records (plus 1 header row)")


if __name__ == "__main__":
    main()
