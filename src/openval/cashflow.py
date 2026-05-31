"""Lease-level cashflow projection.

Turns a `Lease` into a monthly cashflow DataFrame indexed by month-start.

Sign convention (landlord's perspective):
    base_rent              positive    rent collected
    free_rent_abatement    negative    abatement of base_rent during free months
    ti                     negative    tenant improvement outlay
    lc                     negative    leasing commission outlay
    net_rent               base_rent + free_rent_abatement

Rollover handling:
    If a lease carries a ``MarketLeasingAssumption``, ``project_rent_roll``
    auto-expands it into probability-weighted speculative segments after
    ``end_date``. See ``expand_with_mla`` for the math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from openval.lease import (
    ExpenseStructure,
    Lease,
    MarketLeasingAssumption,
    RentStep,
)


@dataclass(frozen=True)
class WeightedLease:
    """A lease (real or speculative) carrying a probability weight.

    The weight is applied to the lease's projected cashflows before summing
    into the rent roll. Real leases carry weight 1.0; MLA-derived segments
    carry the conditional probability of their branch (renewal vs new) times
    the parent's weight.
    """

    weight: float
    lease: Lease


def project_lease(lease: Lease, start: date, end: date) -> pd.DataFrame:
    """Project a single lease's monthly cashflows over [start, end].

    The projection window is independent of the lease term — months outside
    the lease term are zero. This lets multiple leases on different terms be
    projected onto a common timeline and summed.
    """
    months = pd.date_range(start=_first_of_month(start), end=_first_of_month(end), freq="MS")

    base_rent = pd.Series(0.0, index=months)
    free_rent_abatement = pd.Series(0.0, index=months)
    ti = pd.Series(0.0, index=months)
    lc = pd.Series(0.0, index=months)

    area_sf = float(lease.area_sf)

    for ts in months:
        m_date = ts.date()
        if m_date < lease.start_date or m_date >= lease.end_date:
            continue
        annual_psf = float(_active_psf(lease.base_rent_steps, m_date))
        base_rent.loc[ts] = annual_psf * area_sf / 12.0

    if lease.free_rent_months > 0:
        free_window = pd.date_range(
            start=_to_timestamp(lease.start_date),
            periods=lease.free_rent_months,
            freq="MS",
        )
        for ts in free_window:
            if ts in free_rent_abatement.index:
                free_rent_abatement.loc[ts] = -base_rent.loc[ts]

    commencement = _to_timestamp(lease.start_date)

    ti_amount = float(lease.ti_psf) * area_sf
    if ti_amount > 0 and commencement in ti.index:
        ti.loc[commencement] = -ti_amount

    if lease.lc_pct_first_year_rent > 0:
        lc_amount = float(lease.lc_pct_first_year_rent) * _first_year_rent(lease)
        if commencement in lc.index:
            lc.loc[commencement] = -lc_amount

    df = pd.DataFrame(
        {
            "base_rent": base_rent,
            "free_rent_abatement": free_rent_abatement,
            "ti": ti,
            "lc": lc,
        }
    )
    df["net_rent"] = df["base_rent"] + df["free_rent_abatement"]
    return df


def project_rent_roll(leases: list[Lease], start: date, end: date) -> pd.DataFrame:
    """Sum per-lease projections into a single property-level DataFrame.

    Leases carrying a ``MarketLeasingAssumption`` are auto-expanded into
    probability-weighted speculative segments via ``expand_with_mla``.
    """
    if not leases:
        months = pd.date_range(start=_first_of_month(start), end=_first_of_month(end), freq="MS")
        return pd.DataFrame(
            0.0,
            index=months,
            columns=["base_rent", "free_rent_abatement", "ti", "lc", "net_rent"],
        )

    weighted_segments: list[WeightedLease] = []
    for l in leases:
        weighted_segments.extend(expand_with_mla(l, end))

    projections = [
        project_lease(ws.lease, start, end) * ws.weight for ws in weighted_segments
    ]
    return sum(projections[1:], projections[0].copy())


def expand_with_mla(lease: Lease, projection_end: date) -> list[WeightedLease]:
    """Expand a lease into the original + probability-weighted rollover chain.

    If the lease has no ``market_leasing_assumption``, returns ``[(1.0, lease)]``.
    Otherwise, at every rollover up to ``projection_end`` we branch into a
    renewal segment (weight ``p``) and a new-tenant segment (weight ``1-p``),
    where ``p = renewal_probability``. Each branch's segment carries the same
    MLA, so when it expires we branch again — yielding a binary tree of
    weighted segments whose summed weight always equals 1.0.

    The recursion terminates when the next segment would start at or after
    ``projection_end``, keeping the segment count bounded for typical
    5–10 yr holds.
    """
    if lease.market_leasing_assumption is None or lease.end_date >= projection_end:
        return [WeightedLease(weight=1.0, lease=lease)]

    mla = lease.market_leasing_assumption
    p = float(mla.renewal_probability)

    result: list[WeightedLease] = [WeightedLease(weight=1.0, lease=lease)]

    # Renewal branch (weight = p): same suite, picks up immediately at end_date.
    if p > 0:
        renewal_lease = _make_rollover_lease(lease, mla, is_renewal=True)
        for child in expand_with_mla(renewal_lease, projection_end):
            result.append(WeightedLease(weight=p * child.weight, lease=child.lease))

    # New-tenant branch (weight = 1-p): downtime gap, then new lease.
    new_weight = 1.0 - p
    if new_weight > 0:
        new_lease = _make_rollover_lease(lease, mla, is_renewal=False)
        for child in expand_with_mla(new_lease, projection_end):
            result.append(WeightedLease(weight=new_weight * child.weight, lease=child.lease))

    return result


def _make_rollover_lease(
    parent: Lease,
    mla: MarketLeasingAssumption,
    *,
    is_renewal: bool,
) -> Lease:
    """Build the speculative lease that fills the rollover slot.

    Renewal: starts at parent.end_date, market rent minus renewal discount,
    renewal-specific free rent / TI / LC.

    New tenant: starts at parent.end_date + downtime months, full market rent,
    new-specific free rent / TI / LC.
    """
    if is_renewal:
        new_start = parent.end_date
        free_months = mla.free_rent_months_renewal
        ti_psf = mla.ti_psf_renewal
        lc_pct = mla.lc_pct_renewal
        rent_multiplier = Decimal("1") - mla.renewal_market_discount_pct
        suite_suffix = "renew"
    else:
        new_start = _add_months_date(parent.end_date, mla.downtime_months_new)
        free_months = mla.free_rent_months_new
        ti_psf = mla.ti_psf_new
        lc_pct = mla.lc_pct_new
        rent_multiplier = Decimal("1")
        suite_suffix = "new"

    new_end = _add_months_date(new_start, mla.new_term_months)

    # Market rent has been growing at market_rent_growth_pct/yr since parent's
    # original start. We pin the level to the lease's commencement: rent at
    # new_start = market_rent_psf × (1 + growth) ** years_since_parent_origin.
    # That keeps the MLA's market_rent_psf interpretable as "today's market rent".
    years_since_origin = _decimal_years_between(parent.start_date, new_start)
    spot_market_rent = (
        mla.market_rent_psf
        * (Decimal("1") + mla.market_rent_growth_pct) ** years_since_origin
    )

    # In-lease escalation: one step per year at rent_escalation_pct.
    base_rent_steps: list[RentStep] = []
    term_years = max(1, mla.new_term_months // 12)
    for i in range(term_years):
        step_start = _add_months_date(new_start, i * 12)
        if step_start >= new_end:
            break
        step_psf = (
            spot_market_rent
            * rent_multiplier
            * (Decimal("1") + mla.rent_escalation_pct) ** i
        ).quantize(Decimal("0.0001"))
        base_rent_steps.append(RentStep(start_date=step_start, annual_psf=step_psf))
    if not base_rent_steps:
        base_rent_steps.append(
            RentStep(
                start_date=new_start,
                annual_psf=(spot_market_rent * rent_multiplier).quantize(Decimal("0.0001")),
            )
        )

    return Lease(
        suite_id=f"{parent.suite_id}-{suite_suffix}",
        tenant_name=f"{parent.tenant_name} ({suite_suffix})",
        area_sf=parent.area_sf,
        start_date=new_start,
        end_date=new_end,
        base_rent_steps=base_rent_steps,
        free_rent_months=free_months,
        ti_psf=ti_psf,
        lc_pct_first_year_rent=lc_pct,
        expense_structure=mla.expense_structure,
        base_year=new_start.year if mla.expense_structure is ExpenseStructure.MG else None,
        market_leasing_assumption=mla,
    )


def _decimal_years_between(start: date, target: date) -> Decimal:
    """Years between two dates as a Decimal (fractional, month resolution)."""
    months = (target.year - start.year) * 12 + (target.month - start.month)
    return Decimal(months) / Decimal(12)


def _add_months_date(d: date, n: int) -> date:
    year = d.year + (d.month - 1 + n) // 12
    month = (d.month - 1 + n) % 12 + 1
    # Preserve original day if possible (lease.end_date semantics use day=1).
    return date(year, month, min(d.day, 28))


def _active_psf(steps: list[RentStep], on_date: date):
    active = steps[0].annual_psf
    for step in steps:
        if step.start_date <= on_date:
            active = step.annual_psf
        else:
            break
    return active


def _first_year_rent(lease: Lease) -> float:
    """Sum of base rent over the first 12 calendar months of the lease term."""
    total = 0.0
    area_sf = float(lease.area_sf)
    for i in range(12):
        m_date = _add_months(lease.start_date, i)
        if m_date >= lease.end_date:
            break
        annual_psf = float(_active_psf(lease.base_rent_steps, m_date))
        total += annual_psf * area_sf / 12.0
    return total


def _add_months(d: date, n: int) -> date:
    year = d.year + (d.month - 1 + n) // 12
    month = (d.month - 1 + n) % 12 + 1
    return date(year, month, 1)


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _to_timestamp(d: date) -> pd.Timestamp:
    return pd.Timestamp(year=d.year, month=d.month, day=1)
