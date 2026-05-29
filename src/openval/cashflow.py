"""Lease-level cashflow projection.

Turns a `Lease` into a monthly cashflow DataFrame indexed by month-start.

Sign convention (landlord's perspective):
    base_rent              positive    rent collected
    free_rent_abatement    negative    abatement of base_rent during free months
    ti                     negative    tenant improvement outlay
    lc                     negative    leasing commission outlay
    net_rent               base_rent + free_rent_abatement
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from openval.lease import Lease, RentStep


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
    """Sum per-lease projections into a single property-level DataFrame."""
    if not leases:
        months = pd.date_range(start=_first_of_month(start), end=_first_of_month(end), freq="MS")
        return pd.DataFrame(
            0.0,
            index=months,
            columns=["base_rent", "free_rent_abatement", "ti", "lc", "net_rent"],
        )
    projections = [project_lease(l, start, end) for l in leases]
    return sum(projections[1:], projections[0].copy())


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
