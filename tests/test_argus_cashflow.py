"""Tests for the Argus Cash Flow ``.xls`` parser.

Fixtures live in ``validation/fixtures/argus_cashflow/`` (gitignored — real deal
data). Tests skip cleanly when the fixtures aren't present so CI still runs on
a fresh clone.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from openval.io import (
    TOP_LINE_INCOME_ROWS,
    ArgusCashflow,
    read_argus_cashflow_xls,
)


FIXTURE_DIR = Path(__file__).parent.parent / "validation" / "fixtures" / "argus_cashflow"


def _available_fixtures() -> list[Path]:
    if not FIXTURE_DIR.exists():
        return []
    return sorted(FIXTURE_DIR.glob("*_Cash Flow_*.xls"))


FIXTURES = _available_fixtures()
pytestmark = pytest.mark.skipif(
    not FIXTURES, reason="No Argus cashflow fixtures present (drop .xls exports into "
    "validation/fixtures/argus_cashflow/ to enable)"
)


@pytest.fixture(params=FIXTURES, ids=lambda p: p.stem.split("_Cash Flow")[0])
def cashflow(request) -> ArgusCashflow:
    return read_argus_cashflow_xls(request.param)


# ----------------------------------------------------------------------
# Header parsing
# ----------------------------------------------------------------------


def test_header_parsed(cashflow: ArgusCashflow):
    assert cashflow.property_name
    assert cashflow.currency == "USD"
    assert isinstance(cashflow.period_start, date)
    assert isinstance(cashflow.period_end, date)
    assert cashflow.period_start < cashflow.period_end


def test_monthly_grid_is_132_months(cashflow: ArgusCashflow):
    # Every export we've seen is an 11-year (132-month) forecast.
    assert cashflow.monthly.shape[1] == 132
    first = cashflow.monthly.columns[0]
    last = cashflow.monthly.columns[-1]
    assert first.to_pydatetime().date() == cashflow.period_start
    # Last *column* is the start-of-month for month 132, which is the same
    # calendar month as period_end (last day of that month).
    assert last.year == cashflow.period_end.year
    assert last.month == cashflow.period_end.month


# ----------------------------------------------------------------------
# Top-line income schema
# ----------------------------------------------------------------------


def test_top_line_income_rows_all_present(cashflow: ArgusCashflow):
    missing = [r for r in TOP_LINE_INCOME_ROWS if r not in cashflow.monthly.index]
    assert not missing, f"Argus rows missing from parse: {missing}"


def test_section_headers_are_nan(cashflow: ArgusCashflow):
    # Argus emits section headers ("Rental Revenue", "Other Tenant Revenue",
    # "Vacancy & Credit Loss") as label-only rows with no monthly values.
    tli = cashflow.top_line_income("monthly")
    for header in ("Rental Revenue", "Other Tenant Revenue", "Vacancy & Credit Loss"):
        assert tli.loc[header].isna().all(), f"{header} should be a label-only row"


def test_scheduled_base_rent_nets_potential_minus_vacancy_and_free_rent(cashflow: ArgusCashflow):
    # Argus's Rental Revenue subgroup is:
    #     Potential Base Rent + Absorption & Turnover Vacancy + Free Rent
    #     = Scheduled Base Rent (the netted line, shown explicitly)
    # The header row "Rental Revenue" is just a label, not a sum.
    tli = cashflow.top_line_income("annual")
    derived = (
        tli.loc["  Potential Base Rent"]
        + tli.loc["  Absorption & Turnover Vacancy"]
        + tli.loc["  Free Rent"]
    )
    pd.testing.assert_series_equal(
        tli.loc["  Scheduled Base Rent"].rename(None),
        derived.rename(None),
        check_names=False,
        atol=10.0,  # whole-dollar rounding across 12 monthly cells
    )


def test_total_rental_revenue_equals_scheduled_base_rent(cashflow: ArgusCashflow):
    # Argus reports Total Rental Revenue as the bottom-line of the Rental
    # Revenue subgroup, which equals Scheduled Base Rent line-for-line.
    tli = cashflow.top_line_income("annual")
    pd.testing.assert_series_equal(
        tli.loc["Total Rental Revenue"].rename(None),
        tli.loc["  Scheduled Base Rent"].rename(None),
        check_names=False,
        atol=1.0,
    )


def test_potential_gross_revenue_equals_total_tenant_revenue(cashflow: ArgusCashflow):
    # In a building with no "other income" line items, PGR == Total Tenant
    # Revenue (which itself == Total Rental Revenue + Total Other Tenant Rev).
    tli = cashflow.top_line_income("annual")
    pd.testing.assert_series_equal(
        tli.loc["Potential Gross Revenue"].rename(None),
        tli.loc["Total Tenant Revenue"].rename(None),
        check_names=False,
        atol=1.0,
    )


def test_egr_equals_pgr_plus_vacancy_and_credit_loss(cashflow: ArgusCashflow):
    tli = cashflow.top_line_income("annual")
    derived = tli.loc["Potential Gross Revenue"] + tli.loc["Total Vacancy & Credit Loss"]
    pd.testing.assert_series_equal(
        tli.loc["Effective Gross Revenue"].rename(None),
        derived.rename(None),
        check_names=False,
        atol=1.0,
    )


# ----------------------------------------------------------------------
# Cross-check the Argus "Total" column
# ----------------------------------------------------------------------


def test_argus_total_column_matches_monthly_sum(cashflow: ArgusCashflow):
    # Argus rounds each monthly cell to whole dollars, so the row-sum of 132
    # rounded cells can drift from the unrounded Total column. Tolerance is
    # set to $100 per row — empirically we see ~$25 max drift.
    derived = cashflow.monthly.sum(axis=1, min_count=1)
    diff = (derived - cashflow.total).abs().dropna()
    assert (diff < 100.0).all(), f"Argus 'Total' column drifts from monthly sum:\n{diff[diff>=100.0]}"


# ----------------------------------------------------------------------
# Annualization
# ----------------------------------------------------------------------


def test_annual_rollup_shape(cashflow: ArgusCashflow):
    annual = cashflow.top_line_income("annual")
    # 132 months / 12 = exactly 11 fiscal years.
    assert annual.shape[1] == 11
    assert list(annual.columns) == [f"Year {i}" for i in range(1, 12)]


def test_frequency_argument_validated(cashflow: ArgusCashflow):
    with pytest.raises(ValueError):
        cashflow.top_line_income("quarterly")
