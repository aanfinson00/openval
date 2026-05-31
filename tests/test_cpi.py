"""Tests for CPI-indexed lease escalators."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    CpiEscalator,
    ExpenseStructure,
    Lease,
    Property,
    RentStep,
    project_lease,
    project_property,
)


def _cpi_lease() -> Lease:
    return Lease(
        suite_id="A",
        tenant_name="Long Industrial Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2036, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        cpi_escalators=[
            CpiEscalator(effective_date=date(2027, 1, 1), floor_pct=Decimal("0.02"),
                         ceiling_pct=Decimal("0.05")),
            CpiEscalator(effective_date=date(2028, 1, 1), floor_pct=Decimal("0.02"),
                         ceiling_pct=Decimal("0.05")),
        ],
        expense_structure=ExpenseStructure.NNN,
    )


def test_cpi_escalator_applies_within_collar():
    """CPI rate 3% (between 2% floor and 5% ceiling) → 3% bump."""
    cpi = {2027: Decimal("0.03"), 2028: Decimal("0.03")}
    df = project_lease(_cpi_lease(), date(2026, 1, 1), date(2031, 1, 1), cpi_series=cpi)
    # Y1: 30 PSF flat
    y1 = df.loc["2026-06-01", "base_rent"]
    assert y1 == pytest.approx(30 * 50_000 / 12, rel=1e-3)
    # Y2: 30 × 1.03 = 30.90
    y2 = df.loc["2027-06-01", "base_rent"]
    assert y2 == pytest.approx(30.90 * 50_000 / 12, rel=1e-3)
    # Y3: 30.90 × 1.03 = 31.827
    y3 = df.loc["2028-06-01", "base_rent"]
    assert y3 == pytest.approx(31.827 * 50_000 / 12, rel=1e-3)


def test_cpi_floor_kicks_in_when_inflation_too_low():
    """CPI rate 1% → clamped up to 2% floor."""
    cpi = {2027: Decimal("0.01")}
    df = project_lease(_cpi_lease(), date(2026, 1, 1), date(2028, 1, 1), cpi_series=cpi)
    y2 = df.loc["2027-06-01", "base_rent"]
    # 30 × 1.02 = 30.60 (floor applied)
    assert y2 == pytest.approx(30.60 * 50_000 / 12, rel=1e-3)


def test_cpi_ceiling_caps_runaway_inflation():
    """CPI rate 8% → clamped down to 5% ceiling."""
    cpi = {2027: Decimal("0.08")}
    df = project_lease(_cpi_lease(), date(2026, 1, 1), date(2028, 1, 1), cpi_series=cpi)
    y2 = df.loc["2027-06-01", "base_rent"]
    # 30 × 1.05 = 31.50 (ceiling applied)
    assert y2 == pytest.approx(31.50 * 50_000 / 12, rel=1e-3)


def test_missing_cpi_year_skips_escalator():
    """If CPI series lacks the escalator year, no bump for that year."""
    cpi = {}  # empty
    df = project_lease(_cpi_lease(), date(2026, 1, 1), date(2031, 1, 1), cpi_series=cpi)
    # All years stay at $30 PSF since CPI data is missing
    assert df.loc["2027-06-01", "base_rent"] == pytest.approx(30 * 50_000 / 12, rel=1e-3)


def test_existing_rent_step_overrides_cpi_escalator():
    """If a real rent step exists on the escalator date, the step wins."""
    lease = Lease(
        suite_id="A",
        tenant_name="X",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2036, 1, 1),
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30")),
            RentStep(start_date=date(2027, 1, 1), annual_psf=Decimal("35")),  # explicit step
        ],
        cpi_escalators=[
            CpiEscalator(effective_date=date(2027, 1, 1), floor_pct=Decimal("0.02"),
                         ceiling_pct=Decimal("0.05")),
        ],
        expense_structure=ExpenseStructure.NNN,
    )
    df = project_lease(lease, date(2026, 1, 1), date(2028, 1, 1),
                       cpi_series={2027: Decimal("0.03")})
    # Y2 uses explicit step $35 not the CPI-bumped 30 × 1.03
    assert df.loc["2027-06-01", "base_rent"] == pytest.approx(35 * 50_000 / 12, rel=1e-3)


def test_property_passes_cpi_series_through():
    """End-to-end: Property.cpi_series feeds the projector."""
    lease = _cpi_lease()
    prop = Property(
        name="Industrial",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual={y: Decimal("500000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
        cpi_series={
            2027: Decimal("0.025"),
            2028: Decimal("0.025"),
            2029: Decimal("0.03"),
            2030: Decimal("0.03"),
        },
    )
    result = project_property(prop)
    # Y1 gross rent: 30 × 50K = 1.5M
    y1 = result.cashflows.loc["2026-01-01":"2026-12-31", "gross_rent"].sum()
    assert y1 == pytest.approx(1_500_000, rel=1e-3)
    # Y2: should have bumped via CPI
    y2 = result.cashflows.loc["2027-01-01":"2027-12-31", "gross_rent"].sum()
    assert y2 > y1
