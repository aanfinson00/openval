"""Tests for the I/O helpers (rent roll importer, .avux metadata)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from openval import ExpenseStructure
from openval.io import (
    AvuxEncryptedError,
    AvuxMetadata,
    read_avux_metadata,
    read_rent_roll_excel,
)
from openval.io.rent_roll import read_rent_roll_csv


# ----------------------------------------------------------------------
# Rent roll Excel/CSV
# ----------------------------------------------------------------------


def _write_workbook(path: Path, leases_rows: list[dict], rent_steps_rows: list[dict] | None = None) -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(leases_rows).to_excel(writer, sheet_name="leases", index=False)
        if rent_steps_rows is not None:
            pd.DataFrame(rent_steps_rows).to_excel(writer, sheet_name="rent_steps", index=False)


def test_read_rent_roll_excel_minimal_single_lease(tmp_path):
    f = tmp_path / "rr.xlsx"
    _write_workbook(
        f,
        leases_rows=[
            {
                "suite_id": "100",
                "tenant_name": "Acme Logistics",
                "area_sf": 50_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",
                "base_rent_psf": 30.00,
                "expense_structure": "NNN",
            }
        ],
    )
    leases = read_rent_roll_excel(f)
    assert len(leases) == 1
    l = leases[0]
    assert l.suite_id == "100"
    assert l.tenant_name == "Acme Logistics"
    assert l.area_sf == 50_000
    assert l.start_date == date(2026, 1, 1)
    assert l.end_date == date(2031, 1, 1)
    assert l.expense_structure is ExpenseStructure.NNN
    assert len(l.base_rent_steps) == 1
    assert l.base_rent_steps[0].annual_psf == Decimal("30.00")


def test_read_rent_roll_excel_multiple_leases(tmp_path):
    f = tmp_path / "rr.xlsx"
    _write_workbook(
        f,
        leases_rows=[
            {
                "suite_id": "100",
                "tenant_name": "Tenant A",
                "area_sf": 30_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",
                "base_rent_psf": 28,
                "expense_structure": "NNN",
            },
            {
                "suite_id": "200",
                "tenant_name": "Tenant B",
                "area_sf": 20_000,
                "start_date": "2026-06-01",
                "end_date": "2029-06-01",
                "base_rent_psf": 32,
                "expense_structure": "MG",
                "base_year": 2026,
            },
        ],
    )
    leases = read_rent_roll_excel(f)
    assert len(leases) == 2
    assert {l.suite_id for l in leases} == {"100", "200"}
    mg_lease = next(l for l in leases if l.suite_id == "200")
    assert mg_lease.expense_structure is ExpenseStructure.MG
    assert mg_lease.base_year == 2026


def test_rent_steps_sheet_overrides_base_rent_psf(tmp_path):
    f = tmp_path / "rr.xlsx"
    _write_workbook(
        f,
        leases_rows=[
            {
                "suite_id": "100",
                "tenant_name": "Acme",
                "area_sf": 10_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",
                "base_rent_psf": 30,
                "expense_structure": "NNN",
            }
        ],
        rent_steps_rows=[
            {"suite_id": "100", "start_date": "2026-01-01", "annual_psf": 30},
            {"suite_id": "100", "start_date": "2028-01-01", "annual_psf": 32},
            {"suite_id": "100", "start_date": "2030-01-01", "annual_psf": 34},
        ],
    )
    leases = read_rent_roll_excel(f)
    assert len(leases[0].base_rent_steps) == 3
    psfs = [s.annual_psf for s in leases[0].base_rent_steps]
    assert psfs == [Decimal("30"), Decimal("32"), Decimal("34")]


def test_optional_columns_default_correctly(tmp_path):
    f = tmp_path / "rr.xlsx"
    _write_workbook(
        f,
        leases_rows=[
            {
                "suite_id": "100",
                "tenant_name": "Acme",
                "area_sf": 10_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",
                "base_rent_psf": 30,
                "expense_structure": "NNN",
                "free_rent_months": 3,
                "ti_psf": 15,
                "lc_pct_first_year_rent": 0.06,
            }
        ],
    )
    l = read_rent_roll_excel(f)[0]
    assert l.free_rent_months == 3
    assert l.ti_psf == Decimal("15")
    assert l.lc_pct_first_year_rent == Decimal("0.06")


def test_missing_required_column_raises(tmp_path):
    f = tmp_path / "rr.xlsx"
    _write_workbook(
        f,
        leases_rows=[
            {
                "suite_id": "100",
                "tenant_name": "Acme",
                "area_sf": 10_000,
                # missing start_date, end_date, expense_structure
                "base_rent_psf": 30,
            }
        ],
    )
    with pytest.raises(ValueError, match="missing required columns"):
        read_rent_roll_excel(f)


def test_column_names_case_and_space_normalized(tmp_path):
    f = tmp_path / "rr.xlsx"
    pd.DataFrame(
        [
            {
                "Suite ID": "100",
                "Tenant Name": "Acme",
                "Area SF": 10_000,
                "Start Date": "2026-01-01",
                "End Date": "2031-01-01",
                "Base Rent PSF": 30,
                "Expense Structure": "NNN",
            }
        ]
    ).to_excel(f, sheet_name="leases", index=False)
    leases = read_rent_roll_excel(f)
    assert len(leases) == 1
    assert leases[0].tenant_name == "Acme"


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_rent_roll_excel("/no/such/path.xlsx")


def test_csv_reader_minimal(tmp_path):
    f = tmp_path / "rr.csv"
    f.write_text(
        "suite_id,tenant_name,area_sf,start_date,end_date,base_rent_psf,expense_structure\n"
        "100,Acme,50000,2026-01-01,2031-01-01,30.00,NNN\n"
    )
    leases = read_rent_roll_csv(f)
    assert len(leases) == 1
    assert leases[0].suite_id == "100"
    assert leases[0].base_rent_steps[0].annual_psf == Decimal("30.00")


# ----------------------------------------------------------------------
# AVUX
# ----------------------------------------------------------------------

ICLOUD_AVUX = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Claude"


@pytest.mark.skipif(
    not (ICLOUD_AVUX / "12300 Dairy Ashford Rd (2).avux").exists(),
    reason="real .avux fixture not present (skipped on CI)",
)
def test_avux_metadata_extracts_property_header():
    m = read_avux_metadata(ICLOUD_AVUX / "12300 Dairy Ashford Rd (2).avux")
    assert isinstance(m, AvuxMetadata)
    assert m.property_name == "12300 Dairy Ashford Rd (2)"
    assert m.property_type == "Industrial"
    assert m.city == "Sugar Land"
    assert m.state == "TX"
    assert m.analysis_begin == datetime(2023, 1, 1)
    assert m.argus_release == "14.2.0"
    assert m.avux_version == "15.0"


@pytest.mark.skipif(
    not (ICLOUD_AVUX / "12300 Dairy Ashford Rd (2).avux").exists(),
    reason="real .avux fixture not present",
)
def test_avux_metadata_reports_input_encryption():
    """Even when summary says EncryptionMode='None', the Input.xml payload
    is encrypted at the Argus product level. We surface this so callers
    can pivot to .aeex."""
    m = read_avux_metadata(ICLOUD_AVUX / "12300 Dairy Ashford Rd (2).avux")
    assert m.summary_encryption_mode == "None"
    assert m.file_encryption_mode == "Encrypted"


def test_avux_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_avux_metadata("/no/such/path.avux")
