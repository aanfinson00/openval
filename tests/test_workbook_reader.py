"""Tests for ``openval.io.read_property_workbook``.

Uses ``docs/sample_workbook.xlsx`` (built by
``scripts/build_sample_workbook.py``) as the fixture so the reader is
exercised on the same workbook shape the web upload endpoint receives.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from openval import Property
from openval.io import read_property_workbook


WORKBOOK_PATH = Path(__file__).parent.parent / "docs" / "sample_workbook.xlsx"


pytestmark = pytest.mark.skipif(
    not WORKBOOK_PATH.exists(),
    reason="docs/sample_workbook.xlsx missing — run scripts/build_sample_workbook.py first",
)


def test_returns_property_instance():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert isinstance(prop, Property)


def test_property_has_expected_name_and_size():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert prop.name == "Sample Industrial Distribution Center"
    assert prop.rentable_sf == 100_000


def test_leases_and_mlas_are_wired():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert len(prop.leases) >= 1
    for lease in prop.leases:
        assert lease.market_leasing_assumption is not None
        # MLA values from the sample workbook
        assert lease.market_leasing_assumption.market_rent_growth_pct == Decimal("0.03")


def test_opex_capex_schedule_loaded():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert prop.opex_annual
    assert prop.opex_annual[2026] > 0


def test_acquisition_date_parsed():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert prop.acquisition_date == date(2026, 1, 1)


def test_loan_loaded_when_present():
    prop = read_property_workbook(WORKBOOK_PATH)
    assert prop.loan is not None
    assert prop.loan.principal > 0


def test_round_trip_through_engine_runs():
    """Sanity: the workbook → Property → project_property pipeline still
    produces a result (catches regressions in the parser shape)."""
    from openval import project_property
    prop = read_property_workbook(WORKBOOK_PATH)
    result = project_property(prop)
    assert result.cashflows.shape[0] > 0


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_property_workbook("/nonexistent/path/to/workbook.xlsx")
