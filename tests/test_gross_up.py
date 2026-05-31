"""Tests for opex recovery gross-up at low occupancy."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    Property,
    RentStep,
    project_property,
)


def _half_occupied_bldg(gross_up_pct=None) -> Property:
    """100K SF building, single 50K SF NNN tenant → 50% occupancy."""
    lease = Lease(
        suite_id="A",
        tenant_name="Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
    )
    kwargs = dict(
        name="Half",
        rentable_sf=100_000,
        leases=[lease],
        opex_annual={y: Decimal("1000000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )
    if gross_up_pct is not None:
        kwargs["opex_gross_up_at_occupancy_pct"] = gross_up_pct
    return Property(**kwargs)


def test_no_gross_up_default():
    """Without gross-up, recoveries = pro_rata × opex = 50% × 1M = 500k/yr."""
    result = project_property(_half_occupied_bldg())
    year_1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    assert year_1_rec == pytest.approx(500_000.0, rel=1e-4)


def test_gross_up_at_threshold_scales_recoveries():
    """With gross-up to 95%, recoveries = 50% × 1M × (0.95/0.50) = 950k."""
    result = project_property(_half_occupied_bldg(gross_up_pct=Decimal("0.95")))
    year_1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    assert year_1_rec == pytest.approx(950_000.0, rel=1e-4)


def test_gross_up_at_full_occupancy_threshold():
    """With gross-up to 100%, recoveries = 50% × 1M × (1.00/0.50) = 1M."""
    result = project_property(_half_occupied_bldg(gross_up_pct=Decimal("1.00")))
    year_1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    assert year_1_rec == pytest.approx(1_000_000.0, rel=1e-4)


def test_gross_up_does_not_apply_above_threshold():
    """Building at 100% occupancy with gross-up at 95% → no scaling."""
    full_bldg = Property(
        name="Full",
        rentable_sf=100_000,
        leases=[
            Lease(
                suite_id="A",
                tenant_name="T",
                area_sf=100_000,
                start_date=date(2026, 1, 1),
                end_date=date(2031, 1, 1),
                base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
                expense_structure=ExpenseStructure.NNN,
            )
        ],
        opex_annual={y: Decimal("1000000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
        opex_gross_up_at_occupancy_pct=Decimal("0.95"),
    )
    result = project_property(full_bldg)
    year_1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    # Fully occupied → recoveries = full opex
    assert year_1_rec == pytest.approx(1_000_000.0, rel=1e-4)
