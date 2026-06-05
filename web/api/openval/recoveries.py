"""Expense recovery engine — pro-rata pass-throughs of property OpEx to tenants.

Supported structures:
    NNN  — tenant pays pro-rata share of all OpEx
    MG   — tenant pays pro-rata share over a base year OR over an expense stop ($/sf)
    FSG  — tenant pays nothing on recoveries

Optional annual recovery cap (`recovery_cap_pct`) limits year-over-year growth
of the recovery once the lease has at least one prior full year of recoveries.

OpEx is supplied as an annual schedule (pandas Series indexed by integer year)
and distributed evenly across the year's months. Phase 2 will support
non-uniform monthly OpEx and gross-up for partial occupancy.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from openval.lease import ExpenseStructure, Lease


def project_recoveries(
    lease: Lease,
    start: date,
    end: date,
    property_rentable_sf: int,
    opex_annual: pd.Series,
) -> pd.DataFrame:
    """Project monthly expense recoveries for a single lease.

    Returns DataFrame with one column `recovery` (positive = landlord income).
    """
    months = pd.date_range(
        start=_first_of_month(start),
        end=_first_of_month(end),
        freq="MS",
    )
    monthly = pd.Series(0.0, index=months)

    if lease.expense_structure is ExpenseStructure.FSG:
        return pd.DataFrame({"recovery": monthly})

    if property_rentable_sf <= 0:
        raise ValueError("property_rentable_sf must be positive")
    if lease.area_sf > property_rentable_sf:
        raise ValueError("lease area_sf exceeds property_rentable_sf")

    pro_rata = lease.area_sf / property_rentable_sf
    annual_recoveries = _annual_recoveries(lease, pro_rata, property_rentable_sf, opex_annual)

    for ts in months:
        m_date = ts.date()
        if m_date < lease.start_date or m_date >= lease.end_date:
            continue
        annual_rec = annual_recoveries.get(ts.year)
        if annual_rec is None:
            continue
        monthly.loc[ts] = annual_rec / 12.0

    return pd.DataFrame({"recovery": monthly})


def _annual_recoveries(
    lease: Lease,
    pro_rata: float,
    property_rentable_sf: int,
    opex_annual: pd.Series,
) -> dict[int, float]:
    """Compute uncapped + capped annual recovery for each year the lease is active."""
    lease_years = range(lease.start_date.year, lease.end_date.year + 1)
    out: dict[int, float] = {}
    prior_recovery: float | None = None
    cap = float(lease.recovery_cap_pct) if lease.recovery_cap_pct is not None else None

    for year in lease_years:
        if year not in opex_annual.index:
            continue
        opex_y = float(opex_annual.loc[year])
        annual_rec = _uncapped_annual(lease, pro_rata, property_rentable_sf, opex_y, opex_annual)

        if cap is not None and prior_recovery is not None and prior_recovery > 0:
            annual_rec = min(annual_rec, prior_recovery * (1 + cap))

        out[year] = annual_rec
        prior_recovery = annual_rec

    return out


def _uncapped_annual(
    lease: Lease,
    pro_rata: float,
    property_rentable_sf: int,
    opex_y: float,
    opex_annual: pd.Series,
) -> float:
    if lease.expense_structure is ExpenseStructure.NNN:
        return pro_rata * opex_y

    if lease.expense_structure is ExpenseStructure.MG:
        if lease.base_year is not None:
            if lease.base_year not in opex_annual.index:
                raise ValueError(
                    f"lease base_year {lease.base_year} not present in opex_annual schedule"
                )
            opex_base = float(opex_annual.loc[lease.base_year])
            return max(0.0, pro_rata * (opex_y - opex_base))
        # expense stop ($/sf of property)
        stop_total = float(lease.expense_stop_psf) * property_rentable_sf
        return max(0.0, pro_rata * (opex_y - stop_total))

    return 0.0


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)
