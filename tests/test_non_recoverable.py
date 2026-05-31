"""Tests for Property.opex_non_recoverable_pct."""

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


def _build(nonrec_pct=Decimal("0")) -> Property:
    lease = Lease(
        suite_id="A", tenant_name="T", area_sf=50_000,
        start_date=date(2026, 1, 1), end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
    )
    return Property(
        name="Bldg", rentable_sf=50_000, leases=[lease],
        opex_annual={y: Decimal("500000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5, exit_cap_rate=Decimal("0.07"),
        opex_non_recoverable_pct=nonrec_pct,
    )


def test_default_zero_keeps_full_recoveries():
    """0% non-recoverable = current behavior (full recovery)."""
    result = project_property(_build())
    y1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    # Full opex passed through to tenant who occupies 100%
    assert y1_rec == pytest.approx(500_000.0, rel=1e-4)


def test_non_recoverable_share_reduces_recoveries():
    """8% non-recoverable → tenant only pays 92% × 500K = 460K."""
    result = project_property(_build(nonrec_pct=Decimal("0.08")))
    y1_rec = result.cashflows.loc["2026-01-01":"2026-12-31", "recoveries"].sum()
    assert y1_rec == pytest.approx(460_000.0, rel=1e-4)


def test_opex_line_item_still_shows_total():
    """Opex on the cashflow stays at the full $500K — only recoveries are reduced."""
    result = project_property(_build(nonrec_pct=Decimal("0.10")))
    y1_opex = result.cashflows.loc["2026-01-01":"2026-12-31", "opex"].sum()
    # Opex is negative on the cashflow; absolute value should match total
    assert y1_opex == pytest.approx(-500_000.0, rel=1e-4)
    # And NOI drops because recoveries dropped by 50K (10% × 500K)
    y1_noi = result.cashflows.loc["2026-01-01":"2026-12-31", "noi"].sum()
    full = project_property(_build()).cashflows.loc["2026-01-01":"2026-12-31", "noi"].sum()
    assert full - y1_noi == pytest.approx(50_000.0, rel=1e-3)
