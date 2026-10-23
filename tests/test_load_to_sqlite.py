"""Tests for the cleaning logic in scripts/load_to_sqlite.py.

These run on small hand-built frames shaped like the real register, so they
don't need the 100MB CSV to be downloaded.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from load_to_sqlite import (  # noqa: E402
    clean_chunk,
    normalize_property_type,
    parse_price,
    yes_no_to_int,
)


def make_raw(rows):
    columns = [
        "Date of Sale (dd/mm/yyyy)", "Address", "County", "Eircode", "Price (€)",
        "Not Full Market Price", "VAT Exclusive", "Description of Property",
        "Property Size Description",
    ]
    return pd.DataFrame(rows, columns=columns)


def test_parse_price_strips_euro_sign_and_thousands_separators():
    prices = parse_price(pd.Series(["€343,000.00", "€1,250,000.50", "€95000"]))
    assert prices.tolist() == [343000.0, 1250000.5, 95000.0]


def test_parse_price_returns_nan_for_unparseable_values():
    prices = parse_price(pd.Series(["", "n/a"]))
    assert prices.isna().all()


def test_normalize_property_type_handles_english_and_irish():
    raw = pd.Series([
        "New Dwelling house /Apartment",
        "Second-Hand Dwelling house /Apartment",
        "Teach/Árasán Cónaithe Nua",
        "Teach/?ras?n C?naithe Ath?imhe",  # accents lost at source
    ])
    assert normalize_property_type(raw).tolist() == ["New", "Second-Hand", "New", "Second-Hand"]


def test_yes_no_to_int_is_case_and_whitespace_insensitive():
    flags = yes_no_to_int(pd.Series(["Yes", " yes ", "No", None]))
    assert flags.tolist() == [1, 1, 0, 0]


def test_clean_chunk_parses_types_and_drops_unusable_rows():
    raw = make_raw([
        ["01/03/2015", "1 Main St", "Dublin", None, "€300,000.00", "No", "No",
         "Second-Hand Dwelling house /Apartment", None],
        ["31/12/2024", "2 Quay Rd", "Galway", "H91X123", "€410,500.00", "Yes", "Yes",
         "New Dwelling house /Apartment", "greater than or equal to 38 sq metres and less than 125 sq metres"],
        ["not a date", "3 Bad Row", "Cork", None, "€200,000.00", "No", "No",
         "Second-Hand Dwelling house /Apartment", None],
        ["05/05/2020", "4 No Price", "Kerry", None, "", "No", "No",
         "Second-Hand Dwelling house /Apartment", None],
    ])

    clean = clean_chunk(raw)

    assert len(clean) == 2
    assert clean["sale_date"].tolist() == ["2015-03-01", "2024-12-31"]
    assert clean["year"].tolist() == [2015, 2024]
    assert clean["price"].tolist() == [300000.0, 410500.0]
    assert clean["property_type"].tolist() == ["Second-Hand", "New"]
    assert clean["not_full_market_price"].tolist() == [0, 1]
    assert clean["vat_exclusive"].tolist() == [0, 1]
    assert "price_raw" not in clean.columns
