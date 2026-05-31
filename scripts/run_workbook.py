"""Load an Argus-style sample workbook → run OpenVal → write outputs back.

Usage:
    python scripts/run_workbook.py docs/sample_workbook.xlsx

Preserves all input sheets. Overwrites or appends:

    cashflows         monthly DCF detail
    annual_summary    year-by-year NOI / BTCF rollup
    reversion         terminal NOI, gross/net sale, loan payoff
    irr_summary       UNL + LEV IRR under all three conventions; EM
    yield_matrix      year-by-year going-in / current yield on cost
    sensitivity       5x5 grid: exit cap rate × acquisition price (mid-year IRR)
"""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from openval import (
    ExpenseStructure,
    IrrConvention,
    Lease,
    Loan,
    MarketLeasingAssumption,
    Property,
    project_property,
    sensitivity,
)
from openval.io.rent_roll import read_rent_roll_excel


# ----------------------------------------------------------------------
# Sheet readers — each tab maps to a single concept
# ----------------------------------------------------------------------


def _read_kv(path: Path, sheet: str) -> dict:
    df = pd.read_excel(path, sheet_name=sheet, dtype=object)
    df.columns = [c.strip().lower() for c in df.columns]
    return {str(row["field"]).strip(): row["value"] for _, row in df.iterrows()}


def _read_opex(path: Path) -> dict[int, Decimal]:
    df = pd.read_excel(path, sheet_name="opex", dtype=object)
    return {int(r["year"]): Decimal(str(r["annual_opex"])) for _, r in df.iterrows()}


def _read_capex(path: Path) -> dict[int, Decimal]:
    try:
        df = pd.read_excel(path, sheet_name="capex", dtype=object)
    except (ValueError, KeyError):
        return {}
    return {int(r["year"]): Decimal(str(r["annual_capex"])) for _, r in df.iterrows()}


def _read_mla(path: Path) -> dict[str, MarketLeasingAssumption]:
    try:
        df = pd.read_excel(path, sheet_name="mla", dtype=object)
    except (ValueError, KeyError):
        return {}
    out = {}
    for _, r in df.iterrows():
        out[str(r["suite_id"])] = MarketLeasingAssumption(
            market_rent_psf=Decimal(str(r["market_rent_psf"])),
            market_rent_growth_pct=Decimal(str(r["market_rent_growth_pct"])),
            new_term_months=int(r["new_term_months"]),
            rent_escalation_pct=Decimal(str(r["rent_escalation_pct"])),
            free_rent_months_new=int(r["free_rent_months_new"]),
            free_rent_months_renewal=int(r["free_rent_months_renewal"]),
            ti_psf_new=Decimal(str(r["ti_psf_new"])),
            ti_psf_renewal=Decimal(str(r["ti_psf_renewal"])),
            lc_pct_new=Decimal(str(r["lc_pct_new"])),
            lc_pct_renewal=Decimal(str(r["lc_pct_renewal"])),
            renewal_probability=Decimal(str(r["renewal_probability"])),
            downtime_months_new=int(r["downtime_months_new"]),
            renewal_market_discount_pct=Decimal(str(r["renewal_market_discount_pct"])),
            expense_structure=ExpenseStructure(str(r["expense_structure"]).strip().upper()),
        )
    return out


def _coerce_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    return v


def _build_property(path: Path) -> Property:
    prop_kv = _read_kv(path, "property")
    timing_kv = _read_kv(path, "timing")
    purchase_kv = _read_kv(path, "purchase")
    debt_kv = _read_kv(path, "debt")
    vac_kv = _read_kv(path, "vacancy_credit")

    leases = read_rent_roll_excel(path, leases_sheet="leases", rent_steps_sheet="rent_steps")
    mlas = _read_mla(path)
    if mlas:
        leases = [
            l.model_copy(update={"market_leasing_assumption": mlas[l.suite_id]})
            if l.suite_id in mlas
            else l
            for l in leases
        ]

    loan: Optional[Loan] = None
    if debt_kv.get("loan_principal"):
        loan = Loan(
            principal=Decimal(str(debt_kv["loan_principal"])),
            rate_annual=Decimal(str(debt_kv["loan_rate_annual"])),
            amortization_years=int(debt_kv["loan_amortization_years"]),
            term_years=int(debt_kv["loan_term_years"]),
            interest_only_years=int(debt_kv.get("loan_interest_only_years") or 0),
        )

    return Property(
        name=str(prop_kv["name"]),
        rentable_sf=int(prop_kv["rentable_sf"]),
        leases=leases,
        opex_annual=_read_opex(path),
        capex_annual=_read_capex(path),
        acquisition_date=_coerce_date(timing_kv["acquisition_date"]),
        acquisition_price=Decimal(str(purchase_kv["acquisition_price"])),
        hold_years=int(timing_kv["hold_years"]),
        exit_cap_rate=Decimal(str(purchase_kv["exit_cap_rate"])),
        sale_costs_pct=Decimal(str(purchase_kv.get("sale_costs_pct", "0.02"))),
        reversion_basis=str(timing_kv.get("reversion_basis", "trailing")).strip().lower(),
        general_vacancy_pct=Decimal(str(vac_kv.get("general_vacancy_pct", "0"))),
        credit_loss_pct=Decimal(str(vac_kv.get("credit_loss_pct", "0"))),
        loan=loan,
    )


# ----------------------------------------------------------------------
# Output sheet builders
# ----------------------------------------------------------------------


def _annual_summary(cf: pd.DataFrame) -> pd.DataFrame:
    by_year = cf.groupby(cf.index.year).sum()
    by_year.index.name = "year"
    return by_year[
        ["gross_rent", "free_rent_abatement", "general_vacancy", "credit_loss",
         "recoveries", "egi", "opex", "noi", "capex", "ti", "lc",
         "debt_service", "ncf_unlevered", "ncf_levered"]
    ].round(0)


def _irr_summary(result) -> pd.DataFrame:
    rows = []
    for conv in IrrConvention:
        unl = result.irr(convention=conv)
        lev = result.irr(convention=conv, levered=True)
        rows.append(
            {
                "convention": conv.value,
                "unlevered_irr": None if unl is None else round(unl, 4),
                "levered_irr": None if lev is None else round(lev, 4),
            }
        )
    rows.append({
        "convention": "equity_multiple (total CF / equity)",
        "unlevered_irr": round(result.unlevered_equity_multiple, 4),
        "levered_irr": None if result.levered_equity_multiple is None
                       else round(result.levered_equity_multiple, 4),
    })
    return pd.DataFrame(rows)


def _reversion_detail(result) -> pd.DataFrame:
    r = result.reversion
    return pd.DataFrame(
        [
            ("basis", r.basis),
            ("terminal_noi", round(r.terminal_noi, 0)),
            ("gross_sale_price", round(r.gross_sale_price, 0)),
            ("sale_costs", round(r.sale_costs, 0)),
            ("net_sale", round(r.net_sale, 0)),
            ("loan_payoff", round(r.loan_payoff, 0)),
            ("net_sale_to_equity", round(r.net_sale_to_equity, 0)),
        ],
        columns=["field", "value"],
    )


def _yield_matrix(prop: Property, cf: pd.DataFrame) -> pd.DataFrame:
    """Year-by-year going-in cap (NOI/price) — the canonical CRE yield metric."""
    price = float(prop.acquisition_price)
    by_year = cf.groupby(cf.index.year)["noi"].sum()
    rows = []
    for year, noi in by_year.items():
        rows.append(
            {
                "year": year,
                "noi": round(float(noi), 0),
                "yield_on_cost": round(float(noi) / price, 4),
            }
        )
    return pd.DataFrame(rows)


def _sensitivity_grid(prop: Property) -> pd.DataFrame:
    base_price = float(prop.acquisition_price)
    base_cap = float(prop.exit_cap_rate)
    cap_values = [Decimal(str(round(base_cap + d, 4))) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    price_values = [
        Decimal(str(round(base_price * mul, 2)))
        for mul in (0.90, 0.95, 1.00, 1.05, 1.10)
    ]
    grid = sensitivity(
        prop,
        row_axis="exit_cap_rate",
        row_values=cap_values,
        col_axis="acquisition_price",
        col_values=price_values,
        metric="unlevered_irr",
        irr_convention=IrrConvention.ANNUAL_MID_YEAR,
    )
    grid.index = [f"cap {float(c):.3%}" for c in grid.index]
    grid.columns = [f"price ${float(p):,.0f}" for p in grid.columns]
    return grid.round(4)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/run_workbook.py path/to/workbook.xlsx")
    path = Path(sys.argv[1])
    if not path.exists():
        sys.exit(f"workbook not found: {path}")

    prop = _build_property(path)
    result = project_property(prop)

    cf_for_excel = result.cashflows.copy()
    cf_for_excel.index = cf_for_excel.index.strftime("%Y-%m-%d")
    cf_for_excel = cf_for_excel.round(2)

    output_sheets = {
        "cashflows": (cf_for_excel, True),
        "annual_summary": (_annual_summary(result.cashflows), True),
        "reversion": (_reversion_detail(result), False),
        "irr_summary": (_irr_summary(result), False),
        "yield_matrix": (_yield_matrix(prop, result.cashflows), False),
        "sensitivity": (_sensitivity_grid(prop), True),
    }

    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        for name, (df, with_index) in output_sheets.items():
            df.to_excel(writer, sheet_name=name, index=with_index)

    print(f"Wrote outputs to {path}: {', '.join(output_sheets)}")
    print()
    print(f"Property: {prop.name}")
    print(f"  unlevered IRR (monthly):   {result.unlevered_irr:.2%}")
    print(f"  unlevered IRR (mid-year):  {result.irr(convention=IrrConvention.ANNUAL_MID_YEAR):.2%}")
    if result.levered_irr is not None:
        print(f"  levered IRR (monthly):     {result.levered_irr:.2%}")
        print(f"  levered IRR (mid-year):    {result.irr(convention=IrrConvention.ANNUAL_MID_YEAR, levered=True):.2%}")
    print(f"  unlevered EM:              {result.unlevered_equity_multiple:.2f}x")
    print(f"  terminal NOI ({result.reversion.basis}):  ${result.reversion.terminal_noi:,.0f}")
    print(f"  net sale:                  ${result.reversion.net_sale:,.0f}")


if __name__ == "__main__":
    main()
