"""Reporting helpers — derived analyses that sit on top of a projection.

The pure-engine modules (`cashflow`, `recoveries`, `debt`, `dcf`) produce
the raw monthly numbers. This module turns those numbers into per-tenant
summaries, mark-to-market tables, and other answers that acquisitions
teams ask but don't usually live on the cashflow DataFrame itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

import pandas as pd

from openval.cashflow import _active_psf  # type: ignore[attr-defined]
from openval.lease import Lease
from openval.property import Property


def mark_to_market(prop: Property, as_of: Optional[date] = None) -> pd.DataFrame:
    """Per-lease in-place rent vs market rent comparison.

    For each lease, returns the active $/SF on ``as_of`` (defaults to the
    property's acquisition date), the lease's MLA market rent grown to
    ``as_of``, the dollar and percentage delta, and a "over" / "under" tag.

    Leases without an MLA show NaN for the market columns.
    """
    if as_of is None:
        as_of = prop.acquisition_date

    rows = []
    for lease in prop.leases:
        in_place = float(_active_psf(lease.base_rent_steps, as_of))
        mla = lease.market_leasing_assumption
        if mla is None:
            rows.append(
                {
                    "suite_id": lease.suite_id,
                    "tenant_name": lease.tenant_name,
                    "area_sf": lease.area_sf,
                    "in_place_psf": round(in_place, 4),
                    "market_psf": None,
                    "delta_psf": None,
                    "delta_pct": None,
                    "mtm_tag": "no MLA",
                    "annual_delta_dollars": None,
                }
            )
            continue

        years_since_origin = _decimal_years_between(prop.acquisition_date, as_of)
        market = (
            float(mla.market_rent_psf)
            * (1.0 + float(mla.market_rent_growth_pct)) ** float(years_since_origin)
        )
        delta = in_place - market
        delta_pct = (delta / market) if market else 0.0
        tag = "over" if delta > 0 else ("under" if delta < 0 else "at")
        rows.append(
            {
                "suite_id": lease.suite_id,
                "tenant_name": lease.tenant_name,
                "area_sf": lease.area_sf,
                "in_place_psf": round(in_place, 4),
                "market_psf": round(market, 4),
                "delta_psf": round(delta, 4),
                "delta_pct": round(delta_pct, 4),
                "mtm_tag": tag,
                "annual_delta_dollars": round(delta * lease.area_sf, 0),
            }
        )
    return pd.DataFrame(rows)


def rent_roll_summary(prop: Property) -> pd.DataFrame:
    """Standard property-snapshot table: suite, tenant, area, term, in-place PSF, expense structure."""
    rows = []
    for lease in prop.leases:
        in_place = float(_active_psf(lease.base_rent_steps, prop.acquisition_date))
        rows.append(
            {
                "suite_id": lease.suite_id,
                "tenant_name": lease.tenant_name,
                "area_sf": lease.area_sf,
                "start_date": lease.start_date,
                "end_date": lease.end_date,
                "term_months": lease.term_months(),
                "in_place_psf": round(in_place, 4),
                "annual_rent": round(in_place * lease.area_sf, 0),
                "expense_structure": lease.expense_structure.value,
                "free_rent_months": lease.free_rent_months,
                "ti_psf": float(lease.ti_psf),
                "lc_pct_first_year_rent": float(lease.lc_pct_first_year_rent),
            }
        )
    return pd.DataFrame(rows)


def _decimal_years_between(start: date, target: date) -> Decimal:
    months = (target.year - start.year) * 12 + (target.month - start.month)
    return Decimal(months) / Decimal(12)
