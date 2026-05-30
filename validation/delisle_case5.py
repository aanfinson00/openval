"""Validation harness — DeLisle Case 5 (DCF).

Source: JR DeLisle, jCase5_DCFv26.pdf
URL: https://jrdelisle.com/cases_tutorials/Cases/jCase5_DCFv26.pdf

Independent validation: build the DeLisle Case 5 deal in OpenVal and
compare year-by-year NOI, BTCF, loan balance, and IRR to his published
numbers.

Deal:
    Class B office, 17,000 NRA SF, acquired 2009-01-01 for $3,872,167.
    80% LTV ($3,097,734) at 7.5% over 30/30 fully amortizing.
    Single "Master Lease" — full NRA, $27.56/SF Year 1 (gross), 4% growth.
    OpEx = 10% of PGI growing 4%/yr; Property Tax = 8% of PGI growing 3%/yr.
    Vacancy = 10% of PGI (modeled as an expense line — see note 1).
    5-year hold, 10% exit cap, 2% sale costs.

Notes:
    1. DeLisle's vacancy is a phantom allowance (10% of PGI deducted each year).
       OpenVal doesn't model vacancy directly, so we bundle vacancy into OpEx.
       Mathematically equivalent: NOI = GI − (vac+opex+tax) = 0.9·GI − opex − tax.
    2. Lease is FSG (gross): no recoveries. Avoids the recovery-math comparison.
    3. DeLisle uses FORWARD NOI (year N+1) for reversion. OpenVal uses
       trailing-12 NOI. We compute both for the diff. Forward-NOI mode is
       a Phase 2 OpenVal feature.
    4. DeLisle publishes AFTER-tax IRR (14.76%). OpenVal is pre-tax. The
       agent-derived pre-tax targets (from DeLisle's BTCF + reversion) are:
       unlevered ≈ 11.4%, levered ≈ 19.6%.
"""

from datetime import date
from decimal import Decimal

import numpy_financial as npf

from openval import ExpenseStructure, Lease, Loan, Property, RentStep, project_property


# DeLisle's published figures (Schedule I + Reversion table, Y1–Y5)
DELISLE_PUBLISHED = {
    "noi": [337_361, 351_230, 365_666, 380_690, 396_327],
    "btcf": [77_443, 91_313, 105_748, 120_772, 136_409],
    "loan_balance_eoy5": 2_930_996,
    "gross_sale_y5": 4_126_021,         # = NOI_y6 / 10% (forward NOI)
    "net_sale_y5": 4_043_501,           # gross − 2% costs
    "noi_y6_forward": 412_602,
    "irr_y5_after_tax_published": 0.1476,
    # Pre-tax targets derived by stripping DeLisle's tax layer
    "unlevered_irr_pretax_target": 0.114,
    "levered_irr_pretax_target": 0.196,
}


def build_deal() -> Property:
    base_psf = Decimal("468557") / Decimal("17000")  # = 27.5622

    rent_steps = [
        RentStep(
            start_date=date(2009 + i, 1, 1),
            annual_psf=(base_psf * (Decimal("1.04") ** i)).quantize(Decimal("0.0001")),
        )
        for i in range(5)
    ]

    lease = Lease(
        suite_id="MASTER",
        tenant_name="Master Lease",
        area_sf=17_000,
        start_date=date(2009, 1, 1),
        end_date=date(2015, 1, 1),
        base_rent_steps=rent_steps,
        expense_structure=ExpenseStructure.FSG,
    )

    # OpEx schedule: vacancy + opex + tax (each on its own growth rate)
    opex_annual: dict[int, Decimal] = {}
    for i in range(5):
        gi = Decimal("468557") * (Decimal("1.04") ** i)
        vacancy = (gi * Decimal("0.10")).quantize(Decimal("0.01"))
        opex = (Decimal("46856") * (Decimal("1.04") ** i)).quantize(Decimal("0.01"))
        tax = (Decimal("37485") * (Decimal("1.03") ** i)).quantize(Decimal("0.01"))
        opex_annual[2009 + i] = vacancy + opex + tax

    loan = Loan(
        principal=Decimal("3097734"),
        rate_annual=Decimal("0.075"),
        amortization_years=30,
        term_years=30,
        interest_only_years=0,
    )

    return Property(
        name="DeLisle Case 5 - Class B Office",
        rentable_sf=17_000,
        leases=[lease],
        opex_annual=opex_annual,
        acquisition_date=date(2009, 1, 1),
        acquisition_price=Decimal("3872167"),
        hold_years=5,
        exit_cap_rate=Decimal("0.10"),
        sale_costs_pct=Decimal("0.02"),
        loan=loan,
    )


def reconcile_irr_with_forward_noi(prop: Property, result, noi_y6_forward: float):
    """Recompute IRR using forward (Y6) NOI for reversion, to match DeLisle's convention."""
    gross_sale_forward = noi_y6_forward / float(prop.exit_cap_rate)
    sale_costs_forward = gross_sale_forward * float(prop.sale_costs_pct)
    net_sale_forward = gross_sale_forward - sale_costs_forward
    loan_payoff = result.reversion.loan_payoff
    net_to_equity_forward = net_sale_forward - loan_payoff

    cf = result.cashflows
    # Strip out our trailing-12 reversion and add forward-NOI reversion
    ncf_unlevered_no_rev = cf["ncf_unlevered"].copy()
    ncf_levered_no_rev = cf["ncf_levered"].copy()
    terminal_idx = cf.index[-1]
    ncf_unlevered_no_rev.loc[terminal_idx] -= result.reversion.net_sale
    ncf_levered_no_rev.loc[terminal_idx] -= result.reversion.net_sale_to_equity

    # Re-add with forward NOI reversion
    ncf_unlevered_no_rev.loc[terminal_idx] += net_sale_forward
    ncf_levered_no_rev.loc[terminal_idx] += net_to_equity_forward

    initial_equity_unlevered = float(prop.acquisition_price)
    initial_equity_levered = initial_equity_unlevered - float(prop.loan.principal)

    unl_irr = npf.irr([-initial_equity_unlevered] + ncf_unlevered_no_rev.tolist())
    lev_irr = npf.irr([-initial_equity_levered] + ncf_levered_no_rev.tolist())
    unl_irr_annual = (1 + unl_irr) ** 12 - 1
    lev_irr_annual = (1 + lev_irr) ** 12 - 1

    return {
        "gross_sale_forward": gross_sale_forward,
        "net_sale_forward": net_sale_forward,
        "net_to_equity_forward": net_to_equity_forward,
        "unlevered_irr": unl_irr_annual,
        "levered_irr": lev_irr_annual,
    }


def main() -> None:
    prop = build_deal()
    result = project_property(prop)
    cf = result.cashflows

    print("=" * 78)
    print("DELISLE CASE 5 VALIDATION — OPENVAL vs PUBLISHED")
    print("=" * 78)
    print()

    print(f"{'YEAR':<5} {'OPENVAL NOI':>14} {'DELISLE NOI':>14} {'DIFF':>10} {'DIFF %':>8}")
    print("-" * 78)
    for i in range(5):
        year = 2009 + i
        ours = cf[cf.index.year == year]["noi"].sum()
        theirs = DELISLE_PUBLISHED["noi"][i]
        diff = ours - theirs
        diff_pct = diff / theirs * 100 if theirs else 0
        print(f"{year:<5} {ours:>14,.0f} {theirs:>14,.0f} {diff:>10,.0f} {diff_pct:>7.2f}%")
    print()

    print(f"{'YEAR':<5} {'OPENVAL BTCF':>14} {'DELISLE BTCF':>14} {'DIFF':>10} {'DIFF %':>8}")
    print("-" * 78)
    for i in range(5):
        year = 2009 + i
        ours = (cf[cf.index.year == year]["noi"].sum()
                + cf[cf.index.year == year]["debt_service"].sum())
        theirs = DELISLE_PUBLISHED["btcf"][i]
        diff = ours - theirs
        diff_pct = diff / theirs * 100 if theirs else 0
        print(f"{year:<5} {ours:>14,.0f} {theirs:>14,.0f} {diff:>10,.0f} {diff_pct:>7.2f}%")
    print()

    loan_bal_eoy5 = float(cf["loan_balance"].iloc[-1])
    diff = loan_bal_eoy5 - DELISLE_PUBLISHED["loan_balance_eoy5"]
    print(f"Loan balance EOY5:    openval={loan_bal_eoy5:>14,.0f}   delisle={DELISLE_PUBLISHED['loan_balance_eoy5']:>14,.0f}   diff={diff:>10,.0f}")
    print()

    print("=" * 78)
    print("REVERSION COMPARISON")
    print("=" * 78)
    print(f"  OpenVal (trailing-12 NOI / 10%):")
    print(f"    terminal NOI = {result.reversion.terminal_noi:>14,.0f}  (vs DeLisle Y5 NOI = {DELISLE_PUBLISHED['noi'][4]:,})")
    print(f"    gross sale   = {result.reversion.gross_sale_price:>14,.0f}")
    print(f"    net sale     = {result.reversion.net_sale:>14,.0f}")
    print()
    print(f"  DeLisle (forward NOI Y6 / 10%):")
    print(f"    NOI Y6       = {DELISLE_PUBLISHED['noi_y6_forward']:>14,.0f}")
    print(f"    gross sale   = {DELISLE_PUBLISHED['gross_sale_y5']:>14,.0f}")
    print(f"    net sale     = {DELISLE_PUBLISHED['net_sale_y5']:>14,.0f}")
    print()

    forward = reconcile_irr_with_forward_noi(prop, result, DELISLE_PUBLISHED["noi_y6_forward"])
    print(f"  OpenVal recomputed with FORWARD NOI override:")
    print(f"    gross sale   = {forward['gross_sale_forward']:>14,.0f}")
    print(f"    net sale     = {forward['net_sale_forward']:>14,.0f}")
    print()

    print("=" * 78)
    print("IRR COMPARISON")
    print("=" * 78)
    print(f"  OpenVal (trailing-12):    unlevered={result.unlevered_irr:.2%}   levered={result.levered_irr:.2%}")
    print(f"  OpenVal (forward NOI):    unlevered={forward['unlevered_irr']:.2%}   levered={forward['levered_irr']:.2%}")
    print(f"  DeLisle pre-tax target:   unlevered={DELISLE_PUBLISHED['unlevered_irr_pretax_target']:.2%}   levered={DELISLE_PUBLISHED['levered_irr_pretax_target']:.2%}")
    print(f"  DeLisle pub'd after-tax:                                       levered={DELISLE_PUBLISHED['irr_y5_after_tax_published']:.2%}  (not comparable; we're pre-tax)")
    print()

    print(f"  Unlevered IRR diff vs target (forward NOI mode): {(forward['unlevered_irr'] - DELISLE_PUBLISHED['unlevered_irr_pretax_target']) * 100:+.2f} pp")
    print(f"  Levered IRR diff vs target (forward NOI mode):   {(forward['levered_irr'] - DELISLE_PUBLISHED['levered_irr_pretax_target']) * 100:+.2f} pp")
    print()

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  - NOI year-by-year: tight match expected (math is straightforward).")
    print("  - Loan balance EOY5: should match within $100 (amortization math).")
    print("  - Reversion (trailing-12 vs forward): ~4% expected diff = known OpenVal Phase 2 gap.")
    print("  - With forward NOI override, IRR should land within ~50 bps of derived targets.")


if __name__ == "__main__":
    main()
