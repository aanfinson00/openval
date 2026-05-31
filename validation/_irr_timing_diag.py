"""Diagnostic: explore where the OpenVal vs DeLisle IRR gap comes from.

We run the DeLisle Case 5 deal (forward-NOI mode) and compute IRR several ways:
  1. OpenVal default: monthly cashflows, monthly IRR, then (1+r)^12 - 1
  2. Annual buckets, year-end cashflows (Excel default convention)
  3. Annual buckets, mid-year convention (cashflow halfway through year)
  4. Annual buckets, beginning-of-year convention

Then compare against DeLisle pre-tax targets and identify which convention,
if any, lines up. This is throwaway — kept under validation/ for traceability.
"""

from __future__ import annotations

import numpy_financial as npf
import pandas as pd

from delisle_case5 import DELISLE_PUBLISHED, build_deal
from openval import project_property


def monthly_to_annual_buckets(series: pd.Series) -> list[float]:
    """Sum monthly values into calendar-year buckets, ordered by year."""
    by_year = series.groupby(series.index.year).sum()
    return [float(v) for v in by_year.tolist()]


def annual_irr_endofyear(initial_equity: float, annual_cfs: list[float]) -> float:
    """Standard annual IRR: -E at t=0, CFs at t=1,2,..."""
    flows = [-initial_equity] + annual_cfs
    return float(npf.irr(flows))


def annual_irr_midyear(initial_equity: float, annual_cfs: list[float]) -> float:
    """Mid-year convention: each year's CF discounted to t=0.5, 1.5, 2.5, ...

    Closed form via npf.npv is awkward; instead, we shift periods by 0.5 by
    splitting each year's CF into two half-year halves at t=k and t=k+0.5,
    then using a 6-month rate that we biannualize. Simpler: just solve via
    Brent's method.
    """
    from scipy.optimize import brentq

    def npv(r: float) -> float:
        v = -initial_equity
        for k, cf in enumerate(annual_cfs):
            t = k + 0.5  # mid-year
            v += cf / (1.0 + r) ** t
        return v

    return float(brentq(npv, -0.5, 2.0))


def annual_irr_beginofyear(initial_equity: float, annual_cfs: list[float]) -> float:
    """Beginning-of-year (cashflow at t=0 of each year). Year 1 CF is at t=0
    alongside the equity outflow. That's unusual but let's see."""
    flows = [-initial_equity + annual_cfs[0]] + annual_cfs[1:]
    return float(npf.irr(flows))


def monthly_irr_annualized(initial_equity: float, monthly_cfs: list[float]) -> float:
    flows = [-initial_equity] + monthly_cfs
    monthly = npf.irr(flows)
    return float((1 + monthly) ** 12 - 1)


def main() -> None:
    prop = build_deal("forward")
    result = project_property(prop)
    cf = result.cashflows

    initial_equity_unl = float(prop.acquisition_price)
    initial_equity_lev = initial_equity_unl - float(prop.loan.principal)

    # Bucket cashflows annually. Reversion lives in the last month; annual buckets
    # capture it inside the year-5 total.
    annual_unl = monthly_to_annual_buckets(cf["ncf_unlevered"])
    annual_lev = monthly_to_annual_buckets(cf["ncf_levered"])

    monthly_unl = cf["ncf_unlevered"].tolist()
    monthly_lev = cf["ncf_levered"].tolist()

    print("=" * 78)
    print("DELISLE CASE 5 — IRR CONVENTION DIAGNOSTIC (forward-NOI mode)")
    print("=" * 78)
    print()
    print(f"Initial unlevered equity: ${initial_equity_unl:,.0f}")
    print(f"Initial levered equity:   ${initial_equity_lev:,.0f}")
    print()
    print("Annual unlevered CFs (incl reversion in Y5):")
    for i, v in enumerate(annual_unl, start=1):
        print(f"  Y{i}: ${v:>14,.0f}")
    print(f"  SUM:  ${sum(annual_unl):>14,.0f}")
    print()
    print("Annual levered CFs (incl reversion-to-equity in Y5):")
    for i, v in enumerate(annual_lev, start=1):
        print(f"  Y{i}: ${v:>14,.0f}")
    print(f"  SUM:  ${sum(annual_lev):>14,.0f}")
    print()

    targets = {
        "unl": DELISLE_PUBLISHED["unlevered_irr_pretax_target"],
        "lev": DELISLE_PUBLISHED["levered_irr_pretax_target"],
    }

    rows = []
    rows.append((
        "OpenVal current (monthly, annualized)",
        monthly_irr_annualized(initial_equity_unl, monthly_unl),
        monthly_irr_annualized(initial_equity_lev, monthly_lev),
    ))
    rows.append((
        "Annual end-of-year (Excel default)",
        annual_irr_endofyear(initial_equity_unl, annual_unl),
        annual_irr_endofyear(initial_equity_lev, annual_lev),
    ))
    rows.append((
        "Annual mid-year convention",
        annual_irr_midyear(initial_equity_unl, annual_unl),
        annual_irr_midyear(initial_equity_lev, annual_lev),
    ))
    rows.append((
        "Annual beginning-of-year",
        annual_irr_beginofyear(initial_equity_unl, annual_unl),
        annual_irr_beginofyear(initial_equity_lev, annual_lev),
    ))

    print(f"{'Convention':<40} {'UNL IRR':>10} {'Δ vs tgt':>10} {'LEV IRR':>10} {'Δ vs tgt':>10}")
    print("-" * 88)
    for name, unl, lev in rows:
        d_unl = (unl - targets["unl"]) * 100
        d_lev = (lev - targets["lev"]) * 100
        print(f"{name:<40} {unl:>10.2%} {d_unl:>+9.2f}p {lev:>10.2%} {d_lev:>+9.2f}p")
    print()
    print(f"  DeLisle pre-tax target:                    unl={targets['unl']:.2%}   lev={targets['lev']:.2%}")
    print()


if __name__ == "__main__":
    main()
