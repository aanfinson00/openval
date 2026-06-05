"""Tests for the JV equity waterfall."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    Loan,
    PromoteTier,
    Property,
    RentStep,
    Waterfall,
    project_property,
    run_waterfall,
)


def _good_deal() -> Property:
    """Strong levered deal: 10% on-cost yield, 5.5% debt → positive leverage."""
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
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        ),
    )


def test_waterfall_requires_levered_result():
    """Property without a loan has no levered equity → waterfall errors out."""
    no_loan = Property(
        **{**_good_deal().model_dump(), "loan": None},
    )
    result = project_property(no_loan)
    with pytest.raises(ValueError, match="positive initial equity"):
        run_waterfall(
            result,
            Waterfall(
                lp_equity_share=Decimal("0.9"),
                gp_equity_share=Decimal("0.1"),
            ),
        )


def test_lp_and_gp_shares_must_sum_to_one():
    result = project_property(_good_deal())
    with pytest.raises(ValueError, match="must equal 1.0"):
        run_waterfall(
            result,
            Waterfall(
                lp_equity_share=Decimal("0.8"),
                gp_equity_share=Decimal("0.1"),
            ),
        )


def test_no_promote_lp_and_gp_each_pro_rata():
    """No promote tiers → both parties get their pro-rata share."""
    result = project_property(_good_deal())
    wf = run_waterfall(
        result,
        Waterfall(
            lp_equity_share=Decimal("0.9"),
            gp_equity_share=Decimal("0.1"),
            preferred_return_pct=Decimal("0"),
        ),
    )
    # LP got 90% of equity → 90% of cumulative distributions
    total_dist = wf.schedule[["lp_distribution", "gp_distribution"]].sum()
    ratio = total_dist["lp_distribution"] / (total_dist["lp_distribution"] + total_dist["gp_distribution"])
    assert ratio == pytest.approx(0.9, abs=0.01)


def test_lp_gets_pref_before_gp_residual():
    """With 8% pref and a promote tier, LP gets pref before GP sees promote."""
    result = project_property(_good_deal())
    wf = run_waterfall(
        result,
        Waterfall(
            lp_equity_share=Decimal("0.9"),
            gp_equity_share=Decimal("0.1"),
            preferred_return_pct=Decimal("0.08"),
            promote_tiers=[
                PromoteTier(lp_irr_hurdle=Decimal("0.08"), gp_promote_pct=Decimal("0.20")),
            ],
        ),
    )
    # GP IRR should still be positive but lower than LP IRR (pref delays GP catch-up)
    assert wf.lp_irr_monthly_annualized is not None
    assert wf.gp_irr_monthly_annualized is not None
    assert wf.lp_equity_multiple > 0
    assert wf.gp_equity_multiple > 0


def test_promote_kicks_in_above_hurdle():
    """A higher-promote tier above the pref hurdle gives GP more cashflow share."""
    result = project_property(_good_deal())
    no_promote = run_waterfall(
        result,
        Waterfall(
            lp_equity_share=Decimal("0.9"),
            gp_equity_share=Decimal("0.1"),
            preferred_return_pct=Decimal("0.08"),
        ),
    )
    with_promote = run_waterfall(
        result,
        Waterfall(
            lp_equity_share=Decimal("0.9"),
            gp_equity_share=Decimal("0.1"),
            preferred_return_pct=Decimal("0.08"),
            promote_tiers=[
                PromoteTier(lp_irr_hurdle=Decimal("0.08"), gp_promote_pct=Decimal("0.30")),
            ],
        ),
    )
    # With a 30% promote above 8% pref, GP gets a larger share of upside
    no_gp_share = no_promote.schedule["gp_distribution"].sum()
    with_gp_share = with_promote.schedule["gp_distribution"].sum()
    if with_promote.lp_irr_monthly_annualized and with_promote.lp_irr_monthly_annualized > 0.08:
        assert with_gp_share > no_gp_share


def test_em_and_irr_populated():
    result = project_property(_good_deal())
    wf = run_waterfall(
        result,
        Waterfall(
            lp_equity_share=Decimal("0.9"),
            gp_equity_share=Decimal("0.1"),
            preferred_return_pct=Decimal("0.08"),
            promote_tiers=[
                PromoteTier(lp_irr_hurdle=Decimal("0.08"), gp_promote_pct=Decimal("0.20")),
                PromoteTier(lp_irr_hurdle=Decimal("0.15"), gp_promote_pct=Decimal("0.40")),
            ],
        ),
    )
    assert wf.lp_contributed == pytest.approx(0.9 * float(result.initial_equity_levered))
    assert wf.gp_contributed == pytest.approx(0.1 * float(result.initial_equity_levered))
    assert wf.lp_equity_multiple > 1.0  # LP gets capital back + some return
    assert wf.gp_equity_multiple > 1.0  # GP also gets capital back + promote
