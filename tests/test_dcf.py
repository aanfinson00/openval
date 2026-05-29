from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    Loan,
    Property,
    RentStep,
    project_property,
)


def _full_building_nnn() -> Property:
    """One tenant fills 50,000 sf at $30/sf NNN, 5-yr lease, no debt."""
    lease = Lease(
        suite_id="100",
        tenant_name="Solo Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
    )
    return Property(
        name="Test Building",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual={
            2026: Decimal("500000"),
            2027: Decimal("500000"),
            2028: Decimal("500000"),
            2029: Decimal("500000"),
            2030: Decimal("500000"),
        },
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )


def test_noi_full_building_nnn():
    """Gross rent 1.5M + recoveries 500k - opex 500k = NOI 1.5M/yr."""
    result = project_property(_full_building_nnn())
    cf = result.cashflows
    # Year 1 NOI (sum of 12 months)
    year_1 = cf.loc["2026-01-01":"2026-12-31"]
    assert year_1["gross_rent"].sum() == pytest.approx(1_500_000.0)
    assert year_1["recoveries"].sum() == pytest.approx(500_000.0)
    assert year_1["opex"].sum() == pytest.approx(-500_000.0)
    assert year_1["noi"].sum() == pytest.approx(1_500_000.0)


def test_reversion_matches_trailing_noi_over_cap():
    """$1.5M trailing NOI / 7% cap = $21.43M gross sale, less 2% costs."""
    result = project_property(_full_building_nnn())
    assert result.reversion.terminal_noi == pytest.approx(1_500_000.0)
    expected_gross = 1_500_000.0 / 0.07
    assert result.reversion.gross_sale_price == pytest.approx(expected_gross)
    assert result.reversion.sale_costs == pytest.approx(expected_gross * 0.02)
    assert result.reversion.net_sale == pytest.approx(expected_gross * 0.98)


def test_unlevered_irr_positive_and_reasonable():
    """$15M in, $1.5M/yr NOI (10% cap on cost), exit at 7% cap. IRR > entry cap."""
    result = project_property(_full_building_nnn())
    # 10% on cost + cap rate compression = strong IRR
    assert result.unlevered_irr is not None
    assert 0.12 < result.unlevered_irr < 0.25
    # Equity multiple: 5 years of yield (~50%) + reversion (~140% of equity) = ~1.9-2.0x
    assert 1.7 < result.unlevered_equity_multiple < 2.2


def test_no_loan_means_levered_equals_unlevered_metrics_none():
    result = project_property(_full_building_nnn())
    assert result.levered_irr is None
    assert result.levered_equity_multiple is None


def test_with_loan_levered_irr_exceeds_unlevered():
    """Positive leverage: when entry yield > debt cost, levered IRR > unlevered."""
    prop = _full_building_nnn()
    levered = Property(
        **{**prop.model_dump(), "loan": Loan(
            principal=Decimal("9000000"),  # 60% LTV
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        )}
    )
    result = project_property(levered)
    assert result.levered_irr is not None
    assert result.unlevered_irr is not None
    # Entry yield (~10%) > debt cost (5.5%) -> positive leverage
    assert result.levered_irr > result.unlevered_irr


def test_loan_payoff_in_reversion():
    """Loan balance at sale shows up as loan_payoff, reduces net to equity."""
    prop = _full_building_nnn()
    levered = Property(
        **{**prop.model_dump(), "loan": Loan(
            principal=Decimal("9000000"),
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        )}
    )
    result = project_property(levered)
    assert result.reversion.loan_payoff > 8_000_000  # most of principal still outstanding after 5 yrs
    assert result.reversion.loan_payoff < 9_000_000  # but some paid down
    assert result.reversion.net_sale_to_equity == pytest.approx(
        result.reversion.net_sale - result.reversion.loan_payoff
    )


def test_loan_principal_exceeds_price_rejected():
    prop = _full_building_nnn()
    with pytest.raises(ValueError):
        Property(
            **{**prop.model_dump(), "loan": Loan(
                principal=Decimal("20000000"),
                rate_annual=Decimal("0.055"),
                amortization_years=30,
                term_years=10,
            )}
        )


def test_lease_too_big_for_building_rejected():
    with pytest.raises(ValueError):
        Property(
            name="Bad",
            rentable_sf=10_000,
            leases=[Lease(
                suite_id="100",
                tenant_name="Too Big",
                area_sf=20_000,
                start_date=date(2026, 1, 1),
                end_date=date(2031, 1, 1),
                base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
                expense_structure=ExpenseStructure.NNN,
            )],
            opex_annual={2026: Decimal("100000")},
            acquisition_date=date(2026, 1, 1),
            acquisition_price=Decimal("5000000"),
            hold_years=5,
            exit_cap_rate=Decimal("0.07"),
        )
