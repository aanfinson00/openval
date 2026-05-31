"""Tests for percentage rent projection (retail / restaurant deals)."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    PercentageRent,
    Property,
    RentStep,
    project_lease,
    project_property,
)


def _retail_lease(*, sales: dict[int, Decimal], pr: PercentageRent) -> Lease:
    return Lease(
        suite_id="R1",
        tenant_name="Retailer",
        area_sf=5_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("60"))],
        expense_structure=ExpenseStructure.NNN,
        percentage_rent=pr,
        annual_sales=sales,
    )


def test_no_sales_means_no_percentage_rent():
    """A lease with PR config but zero sales should produce zero PR."""
    lease = _retail_lease(
        sales={},
        pr=PercentageRent(natural_breakpoint=True, rate=Decimal("0.06")),
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    assert df["percentage_rent"].sum() == 0.0


def test_natural_breakpoint_below_threshold():
    """Sales below natural breakpoint (annual base / rate) generate no PR."""
    # Base rent: 60 × 5000 = 300_000. Rate 6% → natural BP = 5_000_000.
    lease = _retail_lease(
        sales={2026: Decimal("4_000_000")},
        pr=PercentageRent(natural_breakpoint=True, rate=Decimal("0.06")),
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    year_1_pr = df.loc["2026-01-01":"2026-12-31", "percentage_rent"].sum()
    assert year_1_pr == pytest.approx(0.0)


def test_natural_breakpoint_above_threshold():
    """Sales above natural BP generate PR = (sales − BP) × rate."""
    # Natural BP = 300_000 / 0.06 = 5_000_000. Sales 7_000_000 → PR = 2M × 6% = 120K.
    lease = _retail_lease(
        sales={2026: Decimal("7_000_000")},
        pr=PercentageRent(natural_breakpoint=True, rate=Decimal("0.06")),
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    year_1_pr = df.loc["2026-01-01":"2026-12-31", "percentage_rent"].sum()
    assert year_1_pr == pytest.approx(120_000.0)
    # Monthly should equal 10_000
    assert df.loc["2026-06-01", "percentage_rent"] == pytest.approx(10_000.0)


def test_unnatural_breakpoint():
    """Explicit breakpoint overrides the natural calc."""
    # Sales 5M, unnatural BP 4M, rate 6% → PR = 1M × 6% = 60K.
    lease = _retail_lease(
        sales={2026: Decimal("5_000_000")},
        pr=PercentageRent(
            natural_breakpoint=False,
            breakpoint_annual=Decimal("4_000_000"),
            rate=Decimal("0.06"),
        ),
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    assert df.loc["2026-01-01":"2026-12-31", "percentage_rent"].sum() == pytest.approx(60_000.0)


def test_percentage_rent_flows_to_egi():
    """PR shows up on the property cashflow as part of EGI."""
    lease = _retail_lease(
        sales={2026: Decimal("8_000_000"), 2027: Decimal("8_500_000")},
        pr=PercentageRent(natural_breakpoint=True, rate=Decimal("0.06")),
    )
    prop = Property(
        name="Strip Center",
        rentable_sf=5_000,
        leases=[lease],
        opex_annual={y: Decimal("50000") for y in range(2026, 2031)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("5000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )
    result = project_property(prop)
    # Y1 PR = (8M − 5M) × 6% = 180K
    cf = result.cashflows.loc["2026-01-01":"2026-12-31"]
    assert cf["percentage_rent"].sum() == pytest.approx(180_000.0, rel=1e-4)
    # EGI now includes PR
    expected_egi_y1 = (
        300_000  # base rent
        + 180_000  # percentage rent
        + 50_000  # recoveries (NNN, full building one tenant)
    )
    # No vacancy/credit by default, no free rent in this lease.
    assert cf["egi"].sum() == pytest.approx(expected_egi_y1, rel=1e-3)
