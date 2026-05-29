"""End-to-end DCF: rent roll + recoveries + OpEx -> NOI -> NCF -> reversion -> IRR.

Implements the deterministic CRE DCF core. Rangekeeper would offer the same
math plus stochastic dynamics (Monte Carlo / real options) — we ship the
deterministic path here and keep rangekeeper as an optional Phase 2 swap-in
for the stochastic layer.

Reversion convention: terminal value = trailing-twelve-month NOI / exit cap.
Argus's canonical convention is FORWARD NOI (year N+1) — switching to forward
NOI is a Phase 2 refinement that requires projecting one extra year past the
hold period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy_financial as npf
import pandas as pd

from openval.cashflow import project_rent_roll
from openval.debt import amortize_loan
from openval.property import Property
from openval.recoveries import project_recoveries


@dataclass(frozen=True)
class Reversion:
    terminal_noi: float
    gross_sale_price: float
    sale_costs: float
    net_sale: float
    loan_payoff: float
    net_sale_to_equity: float


@dataclass(frozen=True)
class UnderwritingResult:
    cashflows: pd.DataFrame
    reversion: Reversion
    unlevered_irr: Optional[float]
    levered_irr: Optional[float]
    unlevered_equity_multiple: float
    levered_equity_multiple: Optional[float]


def project_property(prop: Property) -> UnderwritingResult:
    """Run end-to-end underwriting on a property."""
    start = prop.acquisition_date
    end = _add_years(start, prop.hold_years)

    rent_roll = project_rent_roll(prop.leases, start, end)
    expected_months = prop.hold_years * 12
    if len(rent_roll) > expected_months:
        rent_roll = rent_roll.iloc[:expected_months]
    months = rent_roll.index

    opex_series = pd.Series({y: float(v) for y, v in prop.opex_annual.items()})
    capex_series = pd.Series({y: float(v) for y, v in prop.capex_annual.items()}) \
        if prop.capex_annual else pd.Series(dtype=float)

    recoveries_total = _sum_recoveries(prop, start, end, opex_series, months)

    cf = pd.DataFrame(index=months)
    cf["gross_rent"] = rent_roll["base_rent"]
    cf["free_rent_abatement"] = rent_roll["free_rent_abatement"]
    cf["recoveries"] = recoveries_total
    cf["egi"] = cf["gross_rent"] + cf["free_rent_abatement"] + cf["recoveries"]
    cf["opex"] = -_annual_to_monthly(opex_series, months)
    cf["noi"] = cf["egi"] + cf["opex"]
    cf["capex"] = -_annual_to_monthly(capex_series, months) if len(capex_series) else 0.0
    cf["ti"] = rent_roll["ti"]
    cf["lc"] = rent_roll["lc"]
    cf["ncf_unlevered"] = cf["noi"] + cf["capex"] + cf["ti"] + cf["lc"]

    if prop.loan is not None:
        debt = amortize_loan(prop.loan, prop.acquisition_date, months)
        cf["debt_service"] = -debt["payment"]
        cf["loan_balance"] = debt["balance"]
        cf["ncf_levered"] = cf["ncf_unlevered"] + cf["debt_service"]
    else:
        cf["debt_service"] = 0.0
        cf["loan_balance"] = 0.0
        cf["ncf_levered"] = cf["ncf_unlevered"]

    reversion = _compute_reversion(cf, prop)

    terminal_idx = cf.index[-1]
    cf.loc[terminal_idx, "ncf_unlevered"] += reversion.net_sale
    cf.loc[terminal_idx, "ncf_levered"] += reversion.net_sale_to_equity

    initial_equity_unlevered = float(prop.acquisition_price)
    initial_equity_levered = (
        float(prop.acquisition_price) - float(prop.loan.principal)
        if prop.loan is not None
        else initial_equity_unlevered
    )

    unlevered_irr = _monthly_irr_to_annual(
        [-initial_equity_unlevered] + cf["ncf_unlevered"].tolist()
    )
    levered_irr = (
        _monthly_irr_to_annual([-initial_equity_levered] + cf["ncf_levered"].tolist())
        if prop.loan is not None
        else None
    )

    unlevered_em = cf["ncf_unlevered"].sum() / initial_equity_unlevered
    levered_em = (
        cf["ncf_levered"].sum() / initial_equity_levered
        if prop.loan is not None
        else None
    )

    return UnderwritingResult(
        cashflows=cf,
        reversion=reversion,
        unlevered_irr=unlevered_irr,
        levered_irr=levered_irr,
        unlevered_equity_multiple=unlevered_em,
        levered_equity_multiple=levered_em,
    )


def _sum_recoveries(
    prop: Property,
    start: date,
    end: date,
    opex_series: pd.Series,
    months: pd.DatetimeIndex,
) -> pd.Series:
    total = pd.Series(0.0, index=months)
    for lease in prop.leases:
        rec = project_recoveries(
            lease, start, end, prop.rentable_sf, opex_series
        )
        total += rec["recovery"]
    return total


def _compute_reversion(cf: pd.DataFrame, prop: Property) -> Reversion:
    trailing_12_noi = float(cf["noi"].tail(12).sum())
    gross_sale = trailing_12_noi / float(prop.exit_cap_rate)
    sale_costs = gross_sale * float(prop.sale_costs_pct)
    net_sale = gross_sale - sale_costs
    loan_payoff = float(cf["loan_balance"].iloc[-1]) if prop.loan is not None else 0.0
    return Reversion(
        terminal_noi=trailing_12_noi,
        gross_sale_price=gross_sale,
        sale_costs=sale_costs,
        net_sale=net_sale,
        loan_payoff=loan_payoff,
        net_sale_to_equity=net_sale - loan_payoff,
    )


def _annual_to_monthly(annual: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    out = pd.Series(0.0, index=months)
    if annual.empty:
        return out
    for ts in months:
        if ts.year in annual.index:
            out.loc[ts] = float(annual.loc[ts.year]) / 12.0
    return out


def _monthly_irr_to_annual(flows: list[float]) -> Optional[float]:
    monthly = npf.irr(flows)
    if monthly is None or pd.isna(monthly):
        return None
    return (1 + monthly) ** 12 - 1


def _add_years(d: date, n: int) -> date:
    try:
        return date(d.year + n, d.month, d.day)
    except ValueError:
        return date(d.year + n, d.month, 28)
