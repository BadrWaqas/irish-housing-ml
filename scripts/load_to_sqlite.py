"""
Loads and cleans the raw Property Price Register CSV into a SQLite database
at data/processed/housing.db, table `sales`.

Why SQLite instead of just working with the CSV directly in pandas? A few
genuine reasons, not just "because the task says so":
- ~800,000 rows is exactly the size where "load the whole CSV every time
  you open a notebook" starts being annoyingly slow, but is nowhere near
  large enough to need a real database server. SQLite is a single file,
  needs no setup, and answers a filtered/aggregated query (like "average
  price per county per year") far faster than re-scanning a CSV in Python.
- It forces a real schema and real types (dates, numbers) once, at load
  time, instead of every notebook re-parsing "01/01/2010" and "€343,000.00"
  from scratch and risking three slightly different parsing bugs.
- SQL is a genuinely good tool for the first pass of exploration here —
  "average price by county" is a GROUP BY, not a modelling question.

Cleaning decisions made here (and why):
- The source file is encoded as cp1252 (Windows-1252), not UTF-8 — that's
  just what the government system that generates it emits (you can see
  this because the price column header is "Price (<euro sign>)" and only
  cp1252 decodes that byte as "€"). A handful of older rows have Irish-
  language property descriptions where accented characters were already
  lost at the source (stored as literal "?" characters) — a real data
  quality quirk of this register, not something introduced here.
- "Description of Property" only ever distinguishes New vs. Second-Hand
  (not house-vs-apartment, despite the "/Apartment" in every value) and
  appears in both English and Irish depending on the row. We normalize it
  to a single `property_type` column with values "New" / "Second-Hand" by
  checking for "new" / "nua" (Irish for "new") case-insensitively, which
  is robust to the encoding quirks above since plain ASCII "new"/"nua"
  survives them.
- Price arrives as a string like "€343,000.00" and is parsed to a plain
  float in euro.
- We do NOT drop "Not Full Market Price" sales (e.g. transfers between
  family members, often priced well below market) at this stage — they're
  a real, documented part of the register and useful to see in SQL
  exploration (e.g. "what fraction of sales are these?"). They get
  filtered out later, only for the ML model, where they'd actively mislead
  a price predictor. Keeping the full raw signal in the database and doing
  purpose-specific filtering downstream is why the DB and the model's
  training set are two different things.

Usage:
    python scripts/load_to_sqlite.py
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CSV_PATH = RAW_DIR / "PPR-ALL.csv"
DB_PATH = PROCESSED_DIR / "housing.db"

CHUNK_SIZE = 50_000

COLUMN_RENAME = {
    "Date of Sale (dd/mm/yyyy)": "sale_date_raw",
    "Address": "address",
    "County": "county",
    "Eircode": "eircode",
    "Price (€)": "price_raw",
    "Not Full Market Price": "not_full_market_price",
    "VAT Exclusive": "vat_exclusive",
    "Description of Property": "property_type_raw",
    "Property Size Description": "size_description",
}


def parse_price(series: pd.Series) -> pd.Series:
    cleaned = series.str.replace(r"[^\d.]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_property_type(series: pd.Series) -> pd.Series:
    lowered = series.str.lower()
    return lowered.apply(lambda s: "New" if ("new" in s or "nua" in s) else "Second-Hand")


def yes_no_to_int(series: pd.Series) -> pd.Series:
    return (series.str.strip().str.lower() == "yes").astype(int)


def clean_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk.rename(columns=COLUMN_RENAME)

    sale_date = pd.to_datetime(chunk["sale_date_raw"], format="%d/%m/%Y", errors="coerce")
    chunk["sale_date"] = sale_date.dt.strftime("%Y-%m-%d")
    chunk["year"] = sale_date.dt.year

    chunk["price"] = parse_price(chunk["price_raw"])
    chunk["property_type"] = normalize_property_type(chunk["property_type_raw"].fillna(""))
    chunk["not_full_market_price"] = yes_no_to_int(chunk["not_full_market_price"])
    chunk["vat_exclusive"] = yes_no_to_int(chunk["vat_exclusive"])

    chunk = chunk.dropna(subset=["sale_date", "price", "county"])

    return chunk[[
        "sale_date", "year", "address", "county", "eircode", "price",
        "not_full_market_price", "vat_exclusive", "property_type", "size_description",
    ]]


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} not found. Run scripts/download_data.py first.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    total_rows = 0
    total_dropped = 0

    reader = pd.read_csv(CSV_PATH, encoding="cp1252", chunksize=CHUNK_SIZE, dtype=str)
    for i, chunk in enumerate(reader):
        raw_count = len(chunk)
        clean = clean_chunk(chunk)
        total_dropped += raw_count - len(clean)
        clean.to_sql("sales", conn, if_exists="append", index=False)
        total_rows += len(clean)
        print(f"chunk {i + 1}: loaded {len(clean):,} rows (running total {total_rows:,})")

    print("Creating indexes...")
    conn.execute("CREATE INDEX idx_sales_county ON sales(county)")
    conn.execute("CREATE INDEX idx_sales_year ON sales(year)")
    conn.execute("CREATE INDEX idx_sales_property_type ON sales(property_type)")
    conn.commit()
    conn.close()

    print(f"\nDone. {total_rows:,} rows loaded into {DB_PATH}")
    print(f"{total_dropped:,} rows dropped (missing/unparseable date, price, or county)")


if __name__ == "__main__":
    main()
