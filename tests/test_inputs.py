"""Tests for input-construction helpers (``openval.inputs``)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    MarketLeasingAssumption,
    Property,
    RentStep,
    opex_with_pct_of_revenue_fee,
    project_property,
)


def _stub_property(opex: dict[int, Decimal]) -> Property:
    """Single-tenant NNN industrial deal for fee-iteration tests."""
    mla = MarketLeasingAssumption(
        market_rent_psf=Decimal("30"),
        market_rent_growth_pct=Decimal("0.03"),
        new_term_months=60,
        rent_escalation_pct=Decimal("0.03"),
        renewal_probability=Decimal("1.0"),
    )
    lease = Lease(
        suite_id="A",
        tenant_name="Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30")),
        ],
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=mla,
    )
    return Property(
        name="Inputs test",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual=opex,
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("10_000_000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )


def test_zero_pct_returns_base_unchanged():
    base = {2026: Decimal("100000"), 2027: Decimal("103000")}
    out = opex_with_pct_of_revenue_fee(base, Decimal("0"), _stub_property(base))
    assert out == base


def test_helper_converges_to_pct_of_egr():
    """With pct = 4%, the converged opex should equal base + 4% × actual EGR
    for every year (within $1, the convergence tolerance)."""
    base = {2026 + i: Decimal(str(1_000_000 * (1.03 ** i))) for i in range(5)}
    pct = Decimal("0.04")
    out = opex_with_pct_of_revenue_fee(base, pct, _stub_property(base))

    # Verify by running the projector with the converged opex and checking
    # that fee = pct × EGR holds for each year.
    prop = _stub_property(out)
    result = project_property(prop)
    egi_y = result.cashflows["egi"].groupby(result.cashflows.index.year).sum()
    for year, total_opex in out.items():
        fee = float(total_opex) - float(base[year])
        expected_fee = float(pct) * float(egi_y[year])
        assert abs(fee - expected_fee) < 1.0, (
            f"Y{year}: converged fee ${fee:,.2f} ≠ {pct*100}% × EGR "
            f"(${expected_fee:,.2f})"
        )


def test_helper_respects_max_iter():
    """``max_iter=1`` returns after one pass without erroring even if the
    schedule isn't fully converged."""
    base = {2026 + i: Decimal("1000000") for i in range(5)}
    out = opex_with_pct_of_revenue_fee(
        base, Decimal("0.04"), _stub_property(base), max_iter=1
    )
    # After 1 iter, opex = base + 4% × EGR_0 (where EGR_0 was computed off
    # base alone — so fee is slightly underestimated vs. converged).
    assert set(out.keys()) == set(base.keys())
    for v in out.values():
        assert v > Decimal("1000000")  # fee added on top of base


def test_helper_handles_year_with_zero_egi():
    """Years outside the lease term (no revenue) get base opex only."""
    base = {2026: Decimal("1000000"), 2099: Decimal("9999999")}
    out = opex_with_pct_of_revenue_fee(
        base, Decimal("0.04"), _stub_property(base)
    )
    # 2099 is beyond the 5-yr hold so the projector won't see EGI there;
    # opex should equal base.
    assert out[2099] == Decimal("9999999.00")


def test_helper_signature_accepts_float_and_string_pct():
    """``pct_of_revenue`` accepts Decimal, float, or numeric string."""
    base = {2026: Decimal("1000000")}
    a = opex_with_pct_of_revenue_fee(base, 0.04, _stub_property(base))
    b = opex_with_pct_of_revenue_fee(base, "0.04", _stub_property(base))
    c = opex_with_pct_of_revenue_fee(base, Decimal("0.04"), _stub_property(base))
    assert a == b == c
