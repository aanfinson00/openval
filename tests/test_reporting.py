"""Tests for the reporting helpers (mark-to-market, rent roll summary)."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    MarketLeasingAssumption,
    Property,
    RentStep,
    mark_to_market,
    rent_roll_summary,
)


def _mla(market_psf: float = 30.0, growth: float = 0.0) -> MarketLeasingAssumption:
    return MarketLeasingAssumption(
        market_rent_psf=Decimal(str(market_psf)),
        market_rent_growth_pct=Decimal(str(growth)),
        new_term_months=60,
    )


def _lease(suite="A", psf=Decimal("32"), area=50_000, mla=None) -> Lease:
    return Lease(
        suite_id=suite,
        tenant_name=f"Tenant {suite}",
        area_sf=area,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=psf)],
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=mla,
    )


def _prop(leases) -> Property:
    return Property(
        name="Test",
        rentable_sf=200_000,
        leases=leases,
        opex_annual={2026: Decimal("500000")},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("20000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )


def test_mark_to_market_over_market():
    """Lease at $32 PSF vs market $30 → over-market by $2."""
    prop = _prop([_lease(psf=Decimal("32"), mla=_mla(30.0))])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["in_place_psf"] == pytest.approx(32.0)
    assert row["market_psf"] == pytest.approx(30.0)
    assert row["delta_psf"] == pytest.approx(2.0)
    assert row["mtm_tag"] == "over"
    assert row["annual_delta_dollars"] == pytest.approx(100_000)


def test_mark_to_market_under_market():
    """Lease at $25 PSF vs market $30 → under-market."""
    prop = _prop([_lease(psf=Decimal("25"), mla=_mla(30.0))])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["delta_psf"] == pytest.approx(-5.0)
    assert row["mtm_tag"] == "under"


def test_mark_to_market_growth_applied_at_as_of_date():
    """Market rent grows from origin to as_of: $30 × 1.03^2 ≈ $31.83."""
    prop = _prop([_lease(psf=Decimal("32"), mla=_mla(30.0, growth=0.03))])
    mtm = mark_to_market(prop, as_of=date(2028, 1, 1))
    assert mtm.iloc[0]["market_psf"] == pytest.approx(31.827, abs=1e-2)


def test_mark_to_market_no_mla_flagged():
    """Leases without MLA still appear in MTM but market columns are blank."""
    prop = _prop([_lease(mla=None)])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["market_psf"] is None
    assert row["mtm_tag"] == "no MLA"


def test_rent_roll_summary_columns_and_values():
    prop = _prop([_lease(suite="A", psf=Decimal("32"), area=60_000)])
    rr = rent_roll_summary(prop)
    row = rr.iloc[0]
    assert row["suite_id"] == "A"
    assert row["area_sf"] == 60_000
    assert row["term_months"] == 60
    assert row["annual_rent"] == pytest.approx(60_000 * 32)
    assert row["expense_structure"] == "NNN"
