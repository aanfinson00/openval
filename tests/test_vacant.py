"""Tests for vacant-suite handling (lease-up modeling)."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    MarketLeasingAssumption,
    Property,
    RentStep,
    project_property,
)


def _vacant_mla(downtime: int = 6) -> MarketLeasingAssumption:
    """An MLA with renewal_probability=0 — vacant suites only lease to new tenants."""
    return MarketLeasingAssumption(
        market_rent_psf=Decimal("30"),
        market_rent_growth_pct=Decimal("0.03"),
        new_term_months=60,
        rent_escalation_pct=Decimal("0.03"),
        free_rent_months_new=2,
        ti_psf_new=Decimal("15"),
        lc_pct_new=Decimal("0.05"),
        renewal_probability=Decimal("0"),
        downtime_months_new=downtime,
        expense_structure=ExpenseStructure.NNN,
    )


def test_vacant_lease_constructor_accepts_zero_rent():
    """The vacant_at_acquisition classmethod builds a lease with $0 placeholder rent."""
    lease = Lease.vacant_at_acquisition(
        suite_id="C",
        area_sf=20_000,
        acquisition_date=date(2026, 1, 1),
        market_leasing_assumption=_vacant_mla(),
    )
    assert lease.tenant_name == "VACANT"
    assert lease.area_sf == 20_000
    assert lease.base_rent_steps[0].annual_psf == Decimal("0")
    # End-date is acquisition month, start one month earlier
    assert lease.end_date == date(2026, 1, 1)
    assert lease.start_date == date(2025, 12, 1)


def test_vacant_suite_zero_rent_first_few_months():
    """A 6-month downtime means the new tenant arrives in month 7."""
    mla = MarketLeasingAssumption(
        market_rent_psf=Decimal("30"),
        market_rent_growth_pct=Decimal("0"),  # constant rent for simple math
        new_term_months=60,
        free_rent_months_new=2,
        ti_psf_new=Decimal("15"),
        lc_pct_new=Decimal("0.05"),
        renewal_probability=Decimal("0"),
        downtime_months_new=6,
        expense_structure=ExpenseStructure.NNN,
    )
    vacant = Lease.vacant_at_acquisition(
        suite_id="C",
        area_sf=20_000,
        acquisition_date=date(2026, 1, 1),
        market_leasing_assumption=mla,
    )
    prop = Property(
        name="Bldg",
        rentable_sf=20_000,
        leases=[vacant],
        opex_annual={y: Decimal("100000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("4000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )
    result = project_property(prop)
    cf = result.cashflows
    # Months 1-6 (Jan-Jun 2026): downtime, no rent
    early_rent = cf.loc["2026-01-01":"2026-06-30", "gross_rent"].sum()
    assert early_rent == pytest.approx(0.0)
    # Month 7 (Jul 2026): new tenant starts at market rent ($30 PSF) with 2 mo free
    # Gross rent shows up but is fully abated for first 2 months.
    jul = cf.loc["2026-07-01"]
    assert jul["gross_rent"] == pytest.approx(30 * 20_000 / 12, rel=1e-3)
    assert jul["free_rent_abatement"] == pytest.approx(-30 * 20_000 / 12, rel=1e-3)


def test_vacant_suite_with_partial_renewal_probability():
    """If renewal_probability > 0, the renewal segment fills immediately with zero downtime."""
    mla = MarketLeasingAssumption(
        market_rent_psf=Decimal("30"),
        new_term_months=60,
        renewal_probability=Decimal("0.5"),  # half renews immediately
        downtime_months_new=6,
        expense_structure=ExpenseStructure.NNN,
    )
    vacant = Lease.vacant_at_acquisition(
        suite_id="C",
        area_sf=20_000,
        acquisition_date=date(2026, 1, 1),
        market_leasing_assumption=mla,
    )
    prop = Property(
        name="Bldg",
        rentable_sf=20_000,
        leases=[vacant],
        opex_annual={y: Decimal("100000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("4000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )
    result = project_property(prop)
    # Month 1: 50% of suite is "renewed" → 50% × 30 × 20K / 12 = 25K monthly base.
    jan = result.cashflows.loc["2026-01-01", "gross_rent"]
    assert jan == pytest.approx(0.5 * 30 * 20_000 / 12, rel=1e-3)
