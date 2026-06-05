"""Tests for mid-hold refinance."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    Loan,
    Property,
    Refinance,
    RentStep,
    project_property,
)


def _base_prop_with_loan() -> Property:
    lease = Lease(
        suite_id="A",
        tenant_name="Tenant",
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
        opex_annual={y: Decimal("500000") for y in range(2026, 2032)},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
        loan=Loan(
            principal=Decimal("9000000"),
            rate_annual=Decimal("0.07"),  # high rate to make refi attractive
            amortization_years=30,
            term_years=10,
        ),
    )


def test_refinance_at_year_3_swaps_loan_terms():
    """After refi, debt service should reflect the new (lower-rate) loan."""
    prop = _base_prop_with_loan()
    prop = Property(
        **{
            **prop.model_dump(),
            "refinance": Refinance(
                effective_date=date(2029, 1, 1),  # year 3
                new_loan=Loan(
                    principal=Decimal("10000000"),  # cash-out refi
                    rate_annual=Decimal("0.04"),  # rate compression
                    amortization_years=30,
                    term_years=10,
                ),
                prepayment_penalty_pct=Decimal("0.02"),
            ),
        }
    )
    result = project_property(prop)
    cf = result.cashflows
    # Pre-refi debt service ≈ original loan's monthly payment
    pre = -cf.loc["2028-06-01", "debt_service"]
    # Post-refi debt service should be lower because the new rate is lower
    post = -cf.loc["2029-06-01", "debt_service"]
    assert post < pre


def test_refi_proceeds_recorded_at_refi_month():
    """Cash-out refi → positive refi_proceeds = new principal − (old balance × (1+penalty))."""
    prop = _base_prop_with_loan()
    prop = Property(
        **{
            **prop.model_dump(),
            "refinance": Refinance(
                effective_date=date(2029, 1, 1),
                new_loan=Loan(
                    principal=Decimal("10000000"),
                    rate_annual=Decimal("0.04"),
                    amortization_years=30,
                    term_years=10,
                ),
                prepayment_penalty_pct=Decimal("0"),
            ),
        }
    )
    result = project_property(prop)
    proceeds_month = result.cashflows.loc["2029-01-01", "refi_proceeds"]
    # Old loan balance after 36 months of amortization at 7% on $9M
    # is roughly $8.78M. New principal $10M → proceeds ≈ $1.2M.
    assert proceeds_month > 1_000_000
    assert proceeds_month < 1_500_000


def test_prepayment_penalty_reduces_proceeds():
    """A 2% prepayment penalty cuts cash-out proceeds by 2% of old balance."""
    prop = _base_prop_with_loan()
    no_pen = Property(
        **{
            **prop.model_dump(),
            "refinance": Refinance(
                effective_date=date(2029, 1, 1),
                new_loan=Loan(
                    principal=Decimal("10000000"),
                    rate_annual=Decimal("0.04"),
                    amortization_years=30,
                    term_years=10,
                ),
                prepayment_penalty_pct=Decimal("0"),
            ),
        }
    )
    with_pen = Property(
        **{
            **prop.model_dump(),
            "refinance": Refinance(
                effective_date=date(2029, 1, 1),
                new_loan=Loan(
                    principal=Decimal("10000000"),
                    rate_annual=Decimal("0.04"),
                    amortization_years=30,
                    term_years=10,
                ),
                prepayment_penalty_pct=Decimal("0.02"),
            ),
        }
    )
    no_pen_proc = project_property(no_pen).cashflows.loc["2029-01-01", "refi_proceeds"]
    with_pen_proc = project_property(with_pen).cashflows.loc["2029-01-01", "refi_proceeds"]
    # Penalty is 2% of old balance (~$8.78M = ~$175K)
    delta = no_pen_proc - with_pen_proc
    assert 150_000 < delta < 200_000


def test_no_refinance_means_no_proceeds_column_activity():
    prop = _base_prop_with_loan()
    result = project_property(prop)
    assert (result.cashflows["refi_proceeds"] == 0).all()


def test_loan_payoff_at_sale_uses_refi_balance():
    """At end of hold, loan_payoff in reversion should reflect the new loan's balance."""
    prop = _base_prop_with_loan()
    prop = Property(
        **{
            **prop.model_dump(),
            "refinance": Refinance(
                effective_date=date(2029, 1, 1),
                new_loan=Loan(
                    principal=Decimal("10000000"),
                    rate_annual=Decimal("0.04"),
                    amortization_years=30,
                    term_years=10,
                ),
                prepayment_penalty_pct=Decimal("0"),
            ),
        }
    )
    result = project_property(prop)
    # 24 months after refi, new $10M @ 4% / 30 amort balance ≈ $9.66M
    assert 9_500_000 < result.reversion.loan_payoff < 9_750_000
