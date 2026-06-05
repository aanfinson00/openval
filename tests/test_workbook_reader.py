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


# ----------------------------------------------------------------------
# write_property_workbook — round-trip companion
# ----------------------------------------------------------------------


from openval.io import write_property_workbook  # noqa: E402


def test_write_round_trip_preserves_core_property_state(tmp_path):
    orig = read_property_workbook(WORKBOOK_PATH)
    out = tmp_path / "roundtrip.xlsx"
    write_property_workbook(orig, out)
    assert out.exists() and out.stat().st_size > 0

    after = read_property_workbook(out)
    assert after.name == orig.name
    assert after.rentable_sf == orig.rentable_sf
    assert after.acquisition_date == orig.acquisition_date
    assert after.hold_years == orig.hold_years
    assert after.acquisition_price == orig.acquisition_price
    assert after.exit_cap_rate == orig.exit_cap_rate


def test_write_round_trip_preserves_leases_and_schedules(tmp_path):
    orig = read_property_workbook(WORKBOOK_PATH)
    out = tmp_path / "roundtrip.xlsx"
    write_property_workbook(orig, out)
    after = read_property_workbook(out)
    assert len(after.leases) == len(orig.leases)
    for o, a in zip(orig.leases, after.leases):
        assert o.suite_id == a.suite_id
        assert o.area_sf == a.area_sf
        assert o.start_date == a.start_date
        assert o.end_date == a.end_date
    assert after.opex_annual == orig.opex_annual


def test_write_round_trip_preserves_loan(tmp_path):
    orig = read_property_workbook(WORKBOOK_PATH)
    out = tmp_path / "roundtrip.xlsx"
    write_property_workbook(orig, out)
    after = read_property_workbook(out)
    assert (orig.loan is None) == (after.loan is None)
    if orig.loan is not None:
        assert after.loan.principal == orig.loan.principal
        assert after.loan.rate_annual == orig.loan.rate_annual


def test_write_round_trip_through_engine_produces_same_y1_noi(tmp_path):
    """The strongest round-trip check: write, re-read, project, compare."""
    from openval import project_property
    orig = read_property_workbook(WORKBOOK_PATH)
    out = tmp_path / "roundtrip.xlsx"
    write_property_workbook(orig, out)
    after = read_property_workbook(out)
    noi_orig = project_property(orig).cashflows.groupby(
        lambda d: d.year)["noi"].sum().iloc[0]
    noi_after = project_property(after).cashflows.groupby(
        lambda d: d.year)["noi"].sum().iloc[0]
    assert abs(noi_orig - noi_after) < 1.0
