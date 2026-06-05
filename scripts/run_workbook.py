"""Load an Argus-style sample workbook → run OpenVal → write outputs back.

Usage:
    python scripts/run_workbook.py docs/sample_workbook.xlsx

Preserves all input sheets. Overwrites or appends:

    rent_roll_in        property snapshot at acquisition
    mark_to_market      per-lease in-place vs market rent
    cashflows           monthly DCF detail
    annual_summary      year-by-year NOI / BTCF rollup
    cashflow_report     Full Argus "Cash Flow" block (PBR -> Cash Flow
                        Available for Distribution), fiscal-year columns
                        anchored on acquisition_date
    reversion           terminal NOI, gross/net sale, loan payoff
    irr_summary         UNL + LEV IRR under all three conventions; EM
    yield_matrix        year-by-year going-in / current yield on cost
    waterfall_schedule  monthly LP/GP distribution detail
    waterfall_summary   LP/GP contributed, EM, IRR
    sensitivity         5x5 grid: exit cap rate × acquisition price (mid-year IRR)
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
    PromoteTier,
    Property,
    Refinance,
    Waterfall,
    argus_cashflow_report,
    mark_to_market,
    project_property,
    rent_roll_summary,
    run_waterfall,
    sensitivity,
)
from openval.io import read_property_workbook
from openval.io.workbook import _read_kv  # waterfall sheet not in Property


# ----------------------------------------------------------------------
# Waterfall reader — Property construction lives in openval.io.workbook,
# but the workbook also has a waterfall sheet that isn't part of Property
# and stays here.
# ----------------------------------------------------------------------


def _read_waterfall(path: Path) -> Optional[Waterfall]:
    kv = _read_kv(path, "waterfall")
    if not kv or "lp_equity_share" not in kv:
        return None
    tiers: list[PromoteTier] = []
    for i in (1, 2, 3, 4, 5):
        hurdle = kv.get(f"tier{i}_lp_irr_hurdle")
        promote = kv.get(f"tier{i}_gp_promote_pct")
        if hurdle is None or promote is None:
            continue
        if (isinstance(hurdle, float) and pd.isna(hurdle)) or \
           (isinstance(promote, float) and pd.isna(promote)):
            continue
        tiers.append(PromoteTier(
            lp_irr_hurdle=Decimal(str(hurdle)),
            gp_promote_pct=Decimal(str(promote)),
        ))
    return Waterfall(
        lp_equity_share=Decimal(str(kv["lp_equity_share"])),
        gp_equity_share=Decimal(str(kv["gp_equity_share"])),
        preferred_return_pct=Decimal(str(kv.get("preferred_return_pct", "0"))),
        promote_tiers=tiers,
    )


# ----------------------------------------------------------------------
# Output sheet builders
# ----------------------------------------------------------------------


def _annual_summary(cf: pd.DataFrame) -> pd.DataFrame:
    by_year = cf.groupby(cf.index.year).sum()
    by_year.index.name = "year"
    columns = [
        "gross_rent", "free_rent_abatement", "percentage_rent",
        "general_vacancy", "credit_loss", "recoveries", "egi",
        "opex", "noi", "capex", "ti", "lc", "debt_service",
        "refi_proceeds", "ncf_unlevered", "ncf_levered",
    ]
    available = [c for c in columns if c in by_year.columns]
    return by_year[available].round(0)


def _irr_summary(result) -> pd.DataFrame:
    rows = []
    for conv in IrrConvention:
        unl = result.irr(convention=conv)
        lev = result.irr(convention=conv, levered=True)
        rows.append(
            {
                "metric": f"IRR ({conv.value})",
                "unlevered": None if unl is None else round(unl, 4),
                "levered": None if lev is None else round(lev, 4),
            }
        )
    rows.append({
        "metric": "Equity multiple",
        "unlevered": round(result.unlevered_equity_multiple, 4),
        "levered": None if result.levered_equity_multiple is None
                   else round(result.levered_equity_multiple, 4),
    })
    rows.append({
        "metric": "Initial equity",
        "unlevered": round(result.initial_equity_unlevered, 0),
        "levered": None if result.initial_equity_levered is None
                   else round(result.initial_equity_levered, 0),
    })
    rows.append({
        "metric": "Going-in cap rate",
        "unlevered": round(result.going_in_cap, 4),
        "levered": None,
    })
    rows.append({
        "metric": "Stabilized cap rate",
        "unlevered": round(result.stabilized_cap, 4),
        "levered": None,
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


def _waterfall_summary(wf_result) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("lp_contributed", round(wf_result.lp_contributed, 0)),
            ("gp_contributed", round(wf_result.gp_contributed, 0)),
            ("lp_total_distributions", round(wf_result.schedule["lp_distribution"].sum(), 0)),
            ("gp_total_distributions", round(wf_result.schedule["gp_distribution"].sum(), 0)),
            ("lp_equity_multiple",
                round(wf_result.lp_equity_multiple, 4)),
            ("gp_equity_multiple",
                round(wf_result.gp_equity_multiple, 4)),
            ("lp_irr (monthly→annual)",
                None if wf_result.lp_irr_monthly_annualized is None
                else round(wf_result.lp_irr_monthly_annualized, 4)),
            ("gp_irr (monthly→annual)",
                None if wf_result.gp_irr_monthly_annualized is None
                else round(wf_result.gp_irr_monthly_annualized, 4)),
        ],
        columns=["metric", "value"],
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/run_workbook.py path/to/workbook.xlsx")
    path = Path(sys.argv[1])
    if not path.exists():
        sys.exit(f"workbook not found: {path}")

    prop = read_property_workbook(path)
    result = project_property(prop)

    cf_for_excel = result.cashflows.copy()
    cf_for_excel.index = cf_for_excel.index.strftime("%Y-%m-%d")
    cf_for_excel = cf_for_excel.round(2)

    output_sheets: dict[str, tuple[pd.DataFrame, bool]] = {
        "rent_roll_in": (rent_roll_summary(prop), False),
        "mark_to_market": (mark_to_market(prop), False),
        "cashflows": (cf_for_excel, True),
        "annual_summary": (_annual_summary(result.cashflows), True),
        # Full Argus "Cash Flow" report — 34 rows (income through cash flow
        # available for distribution). Fiscal-year columns anchored on
        # acquisition. Sub-rows for opex/capex categories show as blank
        # pending the Phase B schema lift (Property.opex_categories,
        # Property.capex_categories).
        "cashflow_report": (argus_cashflow_report(result, prop).round(0), True),
        "reversion": (_reversion_detail(result), False),
        "irr_summary": (_irr_summary(result), False),
        "yield_matrix": (_yield_matrix(prop, result.cashflows), False),
        "sensitivity": (_sensitivity_grid(prop), True),
    }

    waterfall = _read_waterfall(path)
    if waterfall is not None and result.initial_equity_levered:
        try:
            wf = run_waterfall(result, waterfall)
            wf_sched = wf.schedule.copy()
            wf_sched.index = wf_sched.index.strftime("%Y-%m-%d")
            wf_sched = wf_sched.round(2)
            output_sheets["waterfall_schedule"] = (wf_sched, True)
            output_sheets["waterfall_summary"] = (_waterfall_summary(wf), False)
        except ValueError as e:
            print(f"waterfall skipped: {e}")

    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        for name, (df, with_index) in output_sheets.items():
            df.to_excel(writer, sheet_name=name, index=with_index)

    print(f"Wrote outputs to {path}: {', '.join(output_sheets)}")
    print()
    print(f"Property: {prop.name}")
    print(f"  going-in cap:              {result.going_in_cap:.2%}")
    print(f"  stabilized cap:            {result.stabilized_cap:.2%}")
    print(f"  unlevered IRR (mid-year):  {result.irr(convention=IrrConvention.ANNUAL_MID_YEAR):.2%}")
    if result.levered_irr is not None:
        print(f"  levered IRR (mid-year):    {result.irr(convention=IrrConvention.ANNUAL_MID_YEAR, levered=True):.2%}")
    print(f"  unlevered EM:              {result.unlevered_equity_multiple:.2f}x")
    print(f"  terminal NOI ({result.reversion.basis}):  ${result.reversion.terminal_noi:,.0f}")
    print(f"  net sale:                  ${result.reversion.net_sale:,.0f}")
    if waterfall is not None and "waterfall_summary" in output_sheets:
        print()
        wf_summary_df = output_sheets["waterfall_summary"][0]
        for _, row in wf_summary_df.iterrows():
            print(f"  {row['metric']:<32} {row['value']}")


if __name__ == "__main__":
    main()
