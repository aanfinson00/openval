"""Tests for the sensitivity matrix helper."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from openval import (
    ExpenseStructure,
    IrrConvention,
    Lease,
    Loan,
    Property,
    RentStep,
    sensitivity,
)


def _baseline_prop(loan: bool = False) -> Property:
    lease = Lease(
        suite_id="100",
        tenant_name="Solo",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
    )
    return Property(
        name="Bldg",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual={y: Decimal("500000") for y in range(2026, 2031)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
        loan=Loan(
            principal=Decimal("9000000"),
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        ) if loan else None,
    )


def test_basic_shape_and_axes():
    prop = _baseline_prop()
    grid = sensitivity(
        prop,
        row_axis="exit_cap_rate",
        row_values=[Decimal("0.06"), Decimal("0.07"), Decimal("0.08")],
        col_axis="acquisition_price",
        col_values=[Decimal("14000000"), Decimal("15000000"), Decimal("16000000")],
        metric="unlevered_irr",
    )
    assert isinstance(grid, pd.DataFrame)
    assert grid.shape == (3, 3)
    assert grid.index.tolist() == [Decimal("0.06"), Decimal("0.07"), Decimal("0.08")]


def test_lower_exit_cap_means_higher_irr():
    """Cap compression on exit → higher reversion → higher IRR (monotonic in cap)."""
    prop = _baseline_prop()
    grid = sensitivity(
        prop,
        row_axis="exit_cap_rate",
        row_values=[Decimal("0.06"), Decimal("0.07"), Decimal("0.08")],
        col_axis="acquisition_price",
        col_values=[Decimal("15000000")],
        metric="unlevered_irr",
    )
    # Lower exit cap → higher IRR
    assert grid.iloc[0, 0] > grid.iloc[1, 0] > grid.iloc[2, 0]


def test_higher_price_means_lower_irr():
    prop = _baseline_prop()
    grid = sensitivity(
        prop,
        row_axis="exit_cap_rate",
        row_values=[Decimal("0.07")],
        col_axis="acquisition_price",
        col_values=[Decimal("14000000"), Decimal("15000000"), Decimal("16000000")],
        metric="unlevered_irr",
    )
    assert grid.iloc[0, 0] > grid.iloc[0, 1] > grid.iloc[0, 2]


def test_levered_irr_metric_works_only_with_loan():
    prop = _baseline_prop(loan=True)
    grid = sensitivity(
        prop,
        row_axis="loan_rate",
        row_values=[Decimal("0.045"), Decimal("0.055"), Decimal("0.065")],
        col_axis="loan_principal",
        col_values=[Decimal("7500000"), Decimal("9000000")],
        metric="levered_irr",
    )
    # Cheaper debt → higher levered IRR (positive leverage case here).
    assert grid.iloc[0, 0] > grid.iloc[2, 0]


def test_loan_axes_rejected_without_loan():
    prop = _baseline_prop(loan=False)
    with pytest.raises(ValueError, match="no loan"):
        sensitivity(
            prop,
            row_axis="loan_rate",
            row_values=[Decimal("0.055")],
            col_axis="exit_cap_rate",
            col_values=[Decimal("0.07")],
        )


def test_irr_convention_changes_levered_cells():
    """Switching IRR convention shifts every cell."""
    prop = _baseline_prop(loan=True)
    common_kwargs = dict(
        row_axis="exit_cap_rate",
        row_values=[Decimal("0.07")],
        col_axis="acquisition_price",
        col_values=[Decimal("15000000")],
        metric="levered_irr",
    )
    monthly = sensitivity(prop, **common_kwargs, irr_convention=IrrConvention.MONTHLY_ANNUALIZED)
    mid_year = sensitivity(prop, **common_kwargs, irr_convention=IrrConvention.ANNUAL_MID_YEAR)
    assert monthly.iloc[0, 0] != pytest.approx(mid_year.iloc[0, 0], abs=1e-6)


def test_invalid_axis_rejected():
    prop = _baseline_prop()
    with pytest.raises(ValueError, match="row_axis"):
        sensitivity(
            prop,
            row_axis="nope",
            row_values=[1],
            col_axis="exit_cap_rate",
            col_values=[Decimal("0.07")],
        )


def test_invalid_metric_rejected():
    prop = _baseline_prop()
    with pytest.raises(ValueError, match="metric"):
        sensitivity(
            prop,
            row_axis="exit_cap_rate",
            row_values=[Decimal("0.07")],
            col_axis="acquisition_price",
            col_values=[Decimal("15000000")],
            metric="vibes",
        )


def test_same_axis_for_both_rejected():
    prop = _baseline_prop()
    with pytest.raises(ValueError, match="must differ"):
        sensitivity(
            prop,
            row_axis="exit_cap_rate",
            row_values=[Decimal("0.07")],
            col_axis="exit_cap_rate",
            col_values=[Decimal("0.07")],
        )


def test_original_property_unchanged():
    """Sweeping shouldn't mutate the input property."""
    prop = _baseline_prop()
    original_cap = prop.exit_cap_rate
    sensitivity(
        prop,
        row_axis="exit_cap_rate",
        row_values=[Decimal("0.06"), Decimal("0.08")],
        col_axis="acquisition_price",
        col_values=[Decimal("14000000"), Decimal("16000000")],
    )
    assert prop.exit_cap_rate == original_cap
