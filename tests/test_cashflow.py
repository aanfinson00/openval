from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from openval import (
    ExpenseStructure,
    Lease,
    RentStep,
    project_lease,
    project_rent_roll,
)


def _lease(**overrides) -> Lease:
    defaults = dict(
        suite_id="100",
        tenant_name="Acme Co",
        area_sf=5_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("36.00")),
        ],
        expense_structure=ExpenseStructure.NNN,
    )
    defaults.update(overrides)
    return Lease(**defaults)


def test_monthly_base_rent_matches_annual_psf():
    lease = _lease()
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # 5,000 sf * $36/sf / 12 = $15,000/month
    assert df.loc["2026-01-01", "base_rent"] == pytest.approx(15_000.0)
    assert df.loc["2030-12-01", "base_rent"] == pytest.approx(15_000.0)


def test_zero_outside_lease_term():
    lease = _lease(
        start_date=date(2027, 1, 1),
        end_date=date(2030, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2027, 1, 1), annual_psf=Decimal("36.00"))],
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    assert df.loc["2026-06-01", "base_rent"] == 0.0
    assert df.loc["2030-06-01", "base_rent"] == 0.0
    assert df.loc["2028-06-01", "base_rent"] > 0.0


def test_lease_end_is_exclusive():
    """The end_date month should be zero — lease has expired by then."""
    lease = _lease(end_date=date(2031, 1, 1))
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 6, 1))
    assert df.loc["2030-12-01", "base_rent"] > 0.0
    assert df.loc["2031-01-01", "base_rent"] == 0.0


def test_rent_step_applied_at_correct_month():
    lease = _lease(
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30.00")),
            RentStep(start_date=date(2028, 1, 1), annual_psf=Decimal("36.00")),
        ]
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # Pre-step: 5,000 * 30 / 12 = 12,500
    assert df.loc["2027-12-01", "base_rent"] == pytest.approx(12_500.0)
    # Step month and after: 5,000 * 36 / 12 = 15,000
    assert df.loc["2028-01-01", "base_rent"] == pytest.approx(15_000.0)
    assert df.loc["2028-06-01", "base_rent"] == pytest.approx(15_000.0)


def test_free_rent_zeroes_net_rent():
    lease = _lease(free_rent_months=3)
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # Abatement equals -base_rent for the free months
    assert df.loc["2026-01-01", "free_rent_abatement"] == pytest.approx(-15_000.0)
    assert df.loc["2026-03-01", "free_rent_abatement"] == pytest.approx(-15_000.0)
    # Net rent is zero during free period, full rent after
    assert df.loc["2026-01-01", "net_rent"] == pytest.approx(0.0)
    assert df.loc["2026-03-01", "net_rent"] == pytest.approx(0.0)
    assert df.loc["2026-04-01", "net_rent"] == pytest.approx(15_000.0)


def test_ti_paid_at_commencement():
    lease = _lease(ti_psf=Decimal("50"))
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # 5,000 sf * $50/sf = $250,000 outflow
    assert df.loc["2026-01-01", "ti"] == pytest.approx(-250_000.0)
    assert df.loc["2026-02-01", "ti"] == 0.0


def test_lc_is_pct_of_first_year_rent():
    lease = _lease(lc_pct_first_year_rent=Decimal("0.06"))
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # First-year rent: 12 * 15,000 = 180,000. LC = 6% * 180,000 = 10,800
    assert df.loc["2026-01-01", "lc"] == pytest.approx(-10_800.0)


def test_lc_handles_step_within_first_year():
    """If a step occurs inside the first 12 months, LC should reflect the blended first-year rent."""
    lease = _lease(
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30.00")),
            RentStep(start_date=date(2026, 7, 1), annual_psf=Decimal("36.00")),
        ],
        lc_pct_first_year_rent=Decimal("0.06"),
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # Months 1-6: 5,000 * 30 / 12 = 12,500. Months 7-12: 5,000 * 36 / 12 = 15,000
    # First-year rent: 6 * 12,500 + 6 * 15,000 = 75,000 + 90,000 = 165,000
    # LC: 6% * 165,000 = 9,900
    assert df.loc["2026-01-01", "lc"] == pytest.approx(-9_900.0)


def test_rent_roll_sums_leases():
    a = _lease(suite_id="100", area_sf=5_000)
    b = _lease(suite_id="200", area_sf=10_000)
    df = project_rent_roll([a, b], start=date(2026, 1, 1), end=date(2027, 1, 1))
    # A: 15,000/mo, B: 30,000/mo, total: 45,000/mo
    assert df.loc["2026-06-01", "base_rent"] == pytest.approx(45_000.0)


def test_empty_rent_roll_returns_zero_frame():
    df = project_rent_roll([], start=date(2026, 1, 1), end=date(2027, 1, 1))
    assert (df["base_rent"] == 0.0).all()
    assert list(df.columns) == ["base_rent", "free_rent_abatement", "ti", "lc", "percentage_rent", "net_rent"]


def test_projection_window_clips_lease():
    """A lease starting before or extending after the projection window should still be respected within the window."""
    lease = _lease(
        start_date=date(2024, 1, 1),
        end_date=date(2030, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2024, 1, 1), annual_psf=Decimal("36.00"))],
    )
    df = project_lease(lease, start=date(2026, 1, 1), end=date(2031, 1, 1))
    # TI/LC were "paid" before the window — should not appear
    assert df["ti"].sum() == 0.0
    assert df["lc"].sum() == 0.0
    # Rent during window is non-zero
    assert df.loc["2026-06-01", "base_rent"] > 0.0
    assert df.loc["2030-06-01", "base_rent"] == 0.0


def test_returns_dataframe_with_expected_columns():
    df = project_lease(_lease(), start=date(2026, 1, 1), end=date(2031, 1, 1))
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"base_rent", "free_rent_abatement", "ti", "lc", "percentage_rent", "net_rent"}
    assert isinstance(df.index, pd.DatetimeIndex)
