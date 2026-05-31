"""End-to-end DCF: rent roll + recoveries + OpEx -> NOI -> NCF -> reversion -> IRR.

Implements the deterministic CRE DCF core. Rangekeeper would offer the same
math plus stochastic dynamics (Monte Carlo / real options) — we ship the
deterministic path here and keep rangekeeper as an optional Phase 2 swap-in
for the stochastic layer.

Reversion convention is selectable via ``Property.reversion_basis``:
- "trailing" (default): terminal value = trailing-12-month NOI / exit cap.
- "forward": Argus convention — project NOI for the 12 months *after* the
  hold period and divide by exit cap. Requires opex_annual to cover the
  year following the hold.

IRR convention is selectable per call via ``UnderwritingResult.irr(...)``:
- "monthly_annualized" (default): solve monthly IRR on monthly cashflows,
  then (1 + r_m) ** 12 - 1. Highest granularity.
- "annual_end_of_year": Excel default — sum monthly CFs into calendar-year
  buckets, each at year-end (t = 1, 2, ...).
- "annual_mid_year": Argus/CRE standard — annual buckets at mid-year
  (t = 0.5, 1.5, ...). Approximates monthly cashflow timing in a single
  annual period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional, Union

import numpy_financial as npf
import pandas as pd

from openval.cashflow import expand_with_mla, project_rent_roll
from openval.debt import amortize_loan
from openval.property import Property
from openval.recoveries import project_recoveries


class IrrConvention(str, Enum):
    MONTHLY_ANNUALIZED = "monthly_annualized"
    ANNUAL_END_OF_YEAR = "annual_end_of_year"
    ANNUAL_MID_YEAR = "annual_mid_year"


IrrConventionInput = Union[IrrConvention, str]


@dataclass(frozen=True)
class Reversion:
    terminal_noi: float
    gross_sale_price: float
    sale_costs: float
    net_sale: float
    loan_payoff: float
    net_sale_to_equity: float
    basis: str = "trailing"


@dataclass(frozen=True)
class UnderwritingResult:
    cashflows: pd.DataFrame
    reversion: Reversion
    unlevered_irr: Optional[float]
    levered_irr: Optional[float]
    unlevered_equity_multiple: float
    levered_equity_multiple: Optional[float]
    # Append-only additions (post v0.1.0) — stored to support .irr(convention).
    initial_equity_unlevered: float = 0.0
    initial_equity_levered: Optional[float] = None
    # Stabilized NOI = NOI for the first hold year where ramp items (free rent,
    # TI/LC at commencement, MLA downtime) don't depress NOI. Approximated as
    # year 2 of the hold for most stable deals; falls back to the highest NOI
    # year if year 2 isn't clean.
    stabilized_noi: float = 0.0
    going_in_cap: float = 0.0  # year 1 NOI / acquisition price
    stabilized_cap: float = 0.0  # stabilized NOI / acquisition price

    def irr(
        self,
        convention: IrrConventionInput = IrrConvention.MONTHLY_ANNUALIZED,
        levered: bool = False,
    ) -> Optional[float]:
        """Re-compute IRR under the requested timing convention.

        ``convention="monthly_annualized"`` reproduces the value cached in
        ``unlevered_irr`` / ``levered_irr``. The other conventions bucket
        cashflows annually and solve for annual IRR, useful for matching
        Excel models or Argus' year-end / mid-year yield outputs.
        """
        conv = IrrConvention(convention) if isinstance(convention, str) else convention
        if levered:
            if self.initial_equity_levered is None:
                return None
            equity = self.initial_equity_levered
            cfs = self.cashflows["ncf_levered"]
        else:
            equity = self.initial_equity_unlevered
            cfs = self.cashflows["ncf_unlevered"]
        return _irr_from_monthly(equity, cfs, conv)


def project_property(prop: Property) -> UnderwritingResult:
    """Run end-to-end underwriting on a property."""
    start = prop.acquisition_date
    hold_months = prop.hold_years * 12
    forward_mode = prop.reversion_basis == "forward"
    projection_years = prop.hold_years + (1 if forward_mode else 0)
    end = _add_years(start, projection_years)

    rent_roll = project_rent_roll(prop.leases, start, end)
    expected_total = projection_years * 12
    if len(rent_roll) > expected_total:
        rent_roll = rent_roll.iloc[:expected_total]
    months_all = rent_roll.index

    opex_series = pd.Series({y: float(v) for y, v in prop.opex_annual.items()})
    capex_series = pd.Series({y: float(v) for y, v in prop.capex_annual.items()}) \
        if prop.capex_annual else pd.Series(dtype=float)

    recoveries_total = _sum_recoveries(prop, start, end, opex_series, months_all)

    cf_full = pd.DataFrame(index=months_all)
    cf_full["gross_rent"] = rent_roll["base_rent"]
    cf_full["free_rent_abatement"] = rent_roll["free_rent_abatement"]
    # General vacancy + credit loss: applied to gross potential rent as
    # negative line items. Argus separates vacancy (lost rent from unleased
    # space) from credit loss (uncollected rent from leased space); we
    # follow the same separation but apply both as fractions of gross rent.
    vac_pct = float(prop.general_vacancy_pct)
    cl_pct = float(prop.credit_loss_pct)
    cf_full["general_vacancy"] = -cf_full["gross_rent"] * vac_pct if vac_pct else 0.0
    cf_full["credit_loss"] = -cf_full["gross_rent"] * cl_pct if cl_pct else 0.0
    cf_full["recoveries"] = recoveries_total
    cf_full["egi"] = (
        cf_full["gross_rent"]
        + cf_full["free_rent_abatement"]
        + cf_full["general_vacancy"]
        + cf_full["credit_loss"]
        + cf_full["recoveries"]
    )
    cf_full["opex"] = -_annual_to_monthly(opex_series, months_all)
    cf_full["noi"] = cf_full["egi"] + cf_full["opex"]

    # NOI for the 12 months following the hold (forward mode only).
    forward_noi: Optional[float] = (
        float(cf_full["noi"].iloc[hold_months:hold_months + 12].sum())
        if forward_mode
        else None
    )

    # Truncate cashflows to hold period for IRR/EM and downstream calcs.
    cf = cf_full.iloc[:hold_months].copy()
    months = cf.index

    cf["capex"] = -_annual_to_monthly(capex_series, months) if len(capex_series) else 0.0
    cf["ti"] = rent_roll["ti"].iloc[:hold_months]
    cf["lc"] = rent_roll["lc"].iloc[:hold_months]
    cf["ncf_unlevered"] = cf["noi"] + cf["capex"] + cf["ti"] + cf["lc"]

    if prop.loan is not None:
        debt = amortize_loan(prop.loan, prop.acquisition_date, months)
        cf["debt_service"] = -debt["payment"]
        cf["loan_balance"] = debt["balance"]
        cf["ncf_levered"] = cf["ncf_unlevered"] + cf["debt_service"]
        # DSCR + debt yield, computed on trailing-12 month NOI / debt service.
        # Below 1.0 DSCR signals coverage breach; debt yield below the loan's
        # implied threshold (often 8-10%) signals refi risk.
        ttm_noi = cf["noi"].rolling(window=12, min_periods=1).sum()
        ttm_debt = (-cf["debt_service"]).rolling(window=12, min_periods=1).sum()
        cf["dscr"] = ttm_noi / ttm_debt.replace(0, pd.NA)
        cf["debt_yield"] = ttm_noi / cf["loan_balance"].replace(0, pd.NA)
    else:
        cf["debt_service"] = 0.0
        cf["loan_balance"] = 0.0
        cf["ncf_levered"] = cf["ncf_unlevered"]
        cf["dscr"] = pd.NA
        cf["debt_yield"] = pd.NA

    reversion = _compute_reversion(cf, prop, forward_noi=forward_noi)

    terminal_idx = cf.index[-1]
    cf.loc[terminal_idx, "ncf_unlevered"] += reversion.net_sale
    cf.loc[terminal_idx, "ncf_levered"] += reversion.net_sale_to_equity

    closing_costs = float(prop.acquisition_price) * float(prop.acquisition_costs_pct)
    initial_equity_unlevered = float(prop.acquisition_price) + closing_costs

    # Stabilized NOI: best year-2 NOI (year 1 often has free rent / TI ramp).
    # If hold is < 2 years, fall back to year-1 NOI.
    by_year_noi = cf["noi"].groupby(cf.index.year).sum()
    year_1_noi = float(by_year_noi.iloc[0]) if len(by_year_noi) > 0 else 0.0
    stabilized_noi_val = (
        float(by_year_noi.iloc[1])
        if len(by_year_noi) > 1
        else year_1_noi
    )
    going_in_cap_val = year_1_noi / float(prop.acquisition_price)
    stabilized_cap_val = stabilized_noi_val / float(prop.acquisition_price)
    initial_equity_levered = (
        initial_equity_unlevered - float(prop.loan.principal)
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
        initial_equity_unlevered=initial_equity_unlevered,
        initial_equity_levered=initial_equity_levered if prop.loan is not None else None,
        stabilized_noi=stabilized_noi_val,
        going_in_cap=going_in_cap_val,
        stabilized_cap=stabilized_cap_val,
    )


def _sum_recoveries(
    prop: Property,
    start: date,
    end: date,
    opex_series: pd.Series,
    months: pd.DatetimeIndex,
) -> pd.Series:
    """Sum probability-weighted recoveries across all leases + their rollovers."""
    total = pd.Series(0.0, index=months)
    for lease in prop.leases:
        for ws in expand_with_mla(lease, end):
            rec = project_recoveries(
                ws.lease, start, end, prop.rentable_sf, opex_series
            )
            total += rec["recovery"] * ws.weight
    return total


def _compute_reversion(
    cf: pd.DataFrame,
    prop: Property,
    forward_noi: Optional[float] = None,
) -> Reversion:
    if prop.reversion_basis == "forward":
        if forward_noi is None:
            raise ValueError("forward_noi required when reversion_basis='forward'")
        terminal_noi = forward_noi
    else:
        terminal_noi = float(cf["noi"].tail(12).sum())
    gross_sale = terminal_noi / float(prop.exit_cap_rate)
    sale_costs = gross_sale * float(prop.sale_costs_pct)
    net_sale = gross_sale - sale_costs
    loan_payoff = float(cf["loan_balance"].iloc[-1]) if prop.loan is not None else 0.0
    return Reversion(
        terminal_noi=terminal_noi,
        gross_sale_price=gross_sale,
        sale_costs=sale_costs,
        net_sale=net_sale,
        loan_payoff=loan_payoff,
        net_sale_to_equity=net_sale - loan_payoff,
        basis=prop.reversion_basis,
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


def _irr_from_monthly(
    equity: float,
    monthly_cfs: pd.Series,
    convention: IrrConvention,
) -> Optional[float]:
    if convention is IrrConvention.MONTHLY_ANNUALIZED:
        return _monthly_irr_to_annual([-equity] + monthly_cfs.tolist())

    # Both annual conventions need the cashflows bucketed by calendar year.
    annual = monthly_cfs.groupby(monthly_cfs.index.year).sum().tolist()
    annual = [float(v) for v in annual]

    if convention is IrrConvention.ANNUAL_END_OF_YEAR:
        r = npf.irr([-equity] + annual)
        return None if r is None or pd.isna(r) else float(r)

    if convention is IrrConvention.ANNUAL_MID_YEAR:
        return _solve_annual_mid_year(equity, annual)

    raise ValueError(f"Unknown IRR convention: {convention!r}")


def _solve_annual_mid_year(equity: float, annual_cfs: list[float]) -> Optional[float]:
    """Bisect for r in [-0.5, 5.0] solving NPV(-E at t=0; CFs at t=k+0.5) = 0.

    Uses bisection to avoid adding scipy as a runtime dep. CRE IRRs almost
    always live in [-50%, 500%]; outside that we return None.
    """
    def npv(r: float) -> float:
        if r <= -1.0:
            return float("inf")
        v = -equity
        for k, cf in enumerate(annual_cfs):
            v += cf / (1.0 + r) ** (k + 0.5)
        return v

    lo, hi = -0.499, 5.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        # No sign change in the bracket — IRR undefined or outside range.
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if abs(f_mid) < 1e-10 or (hi - lo) < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def _add_years(d: date, n: int) -> date:
    try:
        return date(d.year + n, d.month, d.day)
    except ValueError:
        return date(d.year + n, d.month, 28)
