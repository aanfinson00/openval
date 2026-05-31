"""Equity waterfall: split levered cashflows between sponsor (GP) and LP.

OpenVal implements the canonical CRE JV waterfall:
- **Pro-rata return of capital** until LP gets back its contributed equity
- **Preferred return** to LP at ``preferred_return_pct`` (annual, compounded
  monthly, on outstanding LP capital balance) until pref is satisfied
- **Promote tiers** above the pref — each tier specifies an IRR hurdle and
  the GP share above that hurdle (cumulative, so a 20% promote on a 12%
  hurdle means GP gets 20% / LP gets 80% of cashflows once LP IRR clears 12%)

This is a deterministic mirror of how Excel waterfalls run: walk through
the monthly cashflows, distribute according to the current bucket, and
move buckets when conditions are met. No optimization tricks — just the
straight-line math practitioners use.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import numpy_financial as npf
import pandas as pd
from pydantic import BaseModel, Field

from openval.dcf import UnderwritingResult


class PromoteTier(BaseModel):
    """A promote tier above the LP preferred return.

    ``lp_irr_hurdle`` is the cumulative LP IRR threshold (annualized). Once
    LP IRR clears this hurdle, residual cashflows split ``gp_promote_pct``
    to GP / ``1 - gp_promote_pct`` to LP. Tiers are evaluated in order
    of increasing hurdle.
    """

    lp_irr_hurdle: Decimal = Field(ge=0, le=1)
    gp_promote_pct: Decimal = Field(gt=0, le=1)


class Waterfall(BaseModel):
    """JV waterfall structure: LP + GP equity, preferred return, promote.

    ``lp_equity_share`` + ``gp_equity_share`` should sum to 1.0 (validated).
    """

    lp_equity_share: Decimal = Field(ge=0, le=1)
    gp_equity_share: Decimal = Field(ge=0, le=1)
    preferred_return_pct: Decimal = Field(default=Decimal("0.08"), ge=0, le=1)
    promote_tiers: list[PromoteTier] = Field(default_factory=list)


@dataclass(frozen=True)
class WaterfallResult:
    schedule: pd.DataFrame  # monthly: lp_distribution, gp_distribution, lp_balance, lp_pref_accrued
    lp_irr_monthly_annualized: Optional[float]
    gp_irr_monthly_annualized: Optional[float]
    lp_equity_multiple: float
    gp_equity_multiple: float
    lp_contributed: float
    gp_contributed: float


def run_waterfall(
    result: UnderwritingResult,
    waterfall: Waterfall,
) -> WaterfallResult:
    """Distribute levered cashflows through the JV waterfall.

    Inputs:
        result.cashflows["ncf_levered"] — monthly cashflow to all equity
        result.initial_equity_levered  — total equity contributed at month 0
        waterfall                      — splits, pref, promote tiers

    Output: monthly distributions to LP and GP, plus per-party IRR + EM.
    """
    if abs(float(waterfall.lp_equity_share) + float(waterfall.gp_equity_share) - 1.0) > 1e-6:
        raise ValueError("lp_equity_share + gp_equity_share must equal 1.0")

    total_equity = float(result.initial_equity_levered or 0.0)
    if total_equity <= 0:
        raise ValueError(
            "Waterfall requires a levered result with positive initial equity; "
            "ensure prop.loan is set"
        )

    lp_contrib = total_equity * float(waterfall.lp_equity_share)
    gp_contrib = total_equity * float(waterfall.gp_equity_share)
    pref_rate_monthly = float(waterfall.preferred_return_pct) / 12.0

    cf = result.cashflows.copy()
    months = cf.index
    lp_dist = pd.Series(0.0, index=months)
    gp_dist = pd.Series(0.0, index=months)
    lp_balance = pd.Series(0.0, index=months)  # outstanding contributed equity
    lp_pref_balance = pd.Series(0.0, index=months)  # accrued unpaid pref

    lp_bal = lp_contrib
    gp_bal = gp_contrib
    lp_pref = 0.0
    # Track LP cashflows for IRR hurdle calc
    lp_cfs: list[float] = [-lp_contrib]
    gp_cfs: list[float] = [-gp_contrib]

    tiers_sorted = sorted(waterfall.promote_tiers, key=lambda t: t.lp_irr_hurdle)

    for ts in months:
        ncf = float(cf.loc[ts, "ncf_levered"])
        # Accrue pref monthly on the outstanding LP balance
        lp_pref += lp_bal * pref_rate_monthly

        if ncf < 0:
            # Equity call — split pro-rata
            lp_share = ncf * float(waterfall.lp_equity_share)
            gp_share = ncf * float(waterfall.gp_equity_share)
            lp_dist.loc[ts] = lp_share
            gp_dist.loc[ts] = gp_share
            lp_bal -= lp_share  # negative cashflow increases capital balance
            gp_bal -= gp_share
            lp_cfs.append(lp_share)
            gp_cfs.append(gp_share)
            lp_balance.loc[ts] = lp_bal
            lp_pref_balance.loc[ts] = lp_pref
            continue

        remaining = ncf
        # Bucket 1: return of LP capital
        if lp_bal > 0 and remaining > 0:
            payment = min(lp_bal, remaining)
            lp_dist.loc[ts] += payment
            lp_bal -= payment
            remaining -= payment

        # Bucket 2: LP preferred return
        if lp_pref > 0 and remaining > 0:
            payment = min(lp_pref, remaining)
            lp_dist.loc[ts] += payment
            lp_pref -= payment
            remaining -= payment

        # Bucket 3: return of GP capital (after LP capital + pref are whole)
        if gp_bal > 0 and remaining > 0:
            payment = min(gp_bal, remaining)
            gp_dist.loc[ts] += payment
            gp_bal -= payment
            remaining -= payment

        # Bucket 4+: promote tiers — split residual based on current LP IRR.
        # With no tiers defined the residual splits pari-passu by equity share,
        # which is the canonical "no carry" structure used in pure JV pari-passu deals.
        if remaining > 0:
            if not tiers_sorted:
                gp_share = remaining * float(waterfall.gp_equity_share)
                lp_share = remaining - gp_share
            else:
                split = _resolve_promote_split(
                    tiers_sorted, lp_cfs, lp_dist.loc[ts], remaining, waterfall
                )
                gp_share = remaining * split.gp_pct
                lp_share = remaining - gp_share
            lp_dist.loc[ts] += lp_share
            gp_dist.loc[ts] += gp_share
            remaining = 0

        lp_cfs.append(float(lp_dist.loc[ts]))
        gp_cfs.append(float(gp_dist.loc[ts]))
        lp_balance.loc[ts] = lp_bal
        lp_pref_balance.loc[ts] = lp_pref

    schedule = pd.DataFrame(
        {
            "lp_distribution": lp_dist,
            "gp_distribution": gp_dist,
            "lp_capital_balance": lp_balance,
            "lp_pref_balance": lp_pref_balance,
        }
    )

    lp_irr = _annualize_monthly_irr(lp_cfs)
    gp_irr = _annualize_monthly_irr(gp_cfs)
    lp_em = sum(c for c in lp_cfs if c > 0) / lp_contrib if lp_contrib else 0.0
    gp_em = sum(c for c in gp_cfs if c > 0) / gp_contrib if gp_contrib else 0.0

    return WaterfallResult(
        schedule=schedule,
        lp_irr_monthly_annualized=lp_irr,
        gp_irr_monthly_annualized=gp_irr,
        lp_equity_multiple=lp_em,
        gp_equity_multiple=gp_em,
        lp_contributed=lp_contrib,
        gp_contributed=gp_contrib,
    )


@dataclass(frozen=True)
class _Split:
    gp_pct: float


def _resolve_promote_split(
    tiers_sorted: list[PromoteTier],
    lp_cfs: list[float],
    already_paid_this_month: float,
    pending: float,
    waterfall: Waterfall,
) -> _Split:
    """Pick the active promote tier based on LP IRR if LP got the full residual.

    Projects an upper bound on LP IRR by assuming LP captures all residual
    cashflow this month, then picks the highest hurdle that bound clears.
    This intentionally over-estimates LP IRR (since promote shifts some
    cashflow to GP), but for monotonic deals that simply selects the right
    tier rather than under-promoting GP. For mid-month tier crossings the
    convention is slightly conservative on LP's behalf — a true iterative
    solver would split the residual chunk-wise, but the practical impact
    on annualized IRRs is in the basis points.
    """
    if not tiers_sorted:
        return _Split(gp_pct=0.0)

    projected_lp = already_paid_this_month + pending
    trial_lp_cfs = lp_cfs + [projected_lp]
    lp_irr_to_date = _annualize_monthly_irr(trial_lp_cfs)
    if lp_irr_to_date is None:
        return _Split(gp_pct=0.0)

    active_gp_pct = 0.0
    for tier in tiers_sorted:
        if lp_irr_to_date >= float(tier.lp_irr_hurdle):
            active_gp_pct = float(tier.gp_promote_pct)
        else:
            break
    return _Split(gp_pct=active_gp_pct)


def _annualize_monthly_irr(cfs: list[float]) -> Optional[float]:
    if len(cfs) < 2:
        return None
    try:
        monthly = npf.irr(cfs)
    except Exception:
        return None
    if monthly is None or pd.isna(monthly):
        return None
    return (1 + monthly) ** 12 - 1
