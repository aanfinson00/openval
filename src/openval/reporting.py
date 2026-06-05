"""Reporting helpers — derived analyses that sit on top of a projection.

The pure-engine modules (`cashflow`, `recoveries`, `debt`, `dcf`) produce
the raw monthly numbers. This module turns those numbers into per-tenant
summaries, mark-to-market tables, and other answers that acquisitions
teams ask but don't usually live on the cashflow DataFrame itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import pandas as pd

from openval.cashflow import _active_psf, project_rent_roll  # type: ignore[attr-defined]
from openval.lease import Lease, RentStep
from openval.property import Property

if TYPE_CHECKING:
    from openval.dcf import UnderwritingResult


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


# ----------------------------------------------------------------------
# Argus-style top-line income report
# ----------------------------------------------------------------------


# Mirrors openval.io.argus_cashflow.TOP_LINE_INCOME_ROWS in order and
# indent, with the same labels Argus uses. Section headers (no indent)
# return NaN in the value columns to preserve the visual hierarchy.
ARGUS_TOP_LINE_ROWS: tuple[str, ...] = (
    "Rental Revenue",
    "  Potential Base Rent",
    "  Absorption & Turnover Vacancy",
    "  Free Rent",
    "  Scheduled Base Rent",
    "Total Rental Revenue",
    "Other Tenant Revenue",
    "  Total Expense Recoveries",
    "Total Other Tenant Revenue",
    "Total Tenant Revenue",
    "Potential Gross Revenue",
    "Vacancy & Credit Loss",
    "  Vacancy Allowance",
    "  Credit Loss",
    "Total Vacancy & Credit Loss",
    "Effective Gross Revenue",
)


# Lower block of the Argus cashflow report — opex through cash flow available
# for distribution. Sub-rows for opex categories (Real Estate Taxes, Insurance,
# Property Management Fee, CAM) and capex categories (Capital Reserves vs
# Non-Leasing Capital Expense) need a schema lift on Property — they come back
# as NaN until ``Property.opex_categories`` and ``Property.capex_categories``
# are added (Phase B). "Non-Leasing Capital Expense" defaults to the full
# ``capex_annual`` so single-bucket users still see their capex.
ARGUS_CASHFLOW_LOWER_ROWS: tuple[str, ...] = (
    "Operating Expenses",
    "  Real Estate Taxes",
    "  Insurance",
    "  Property Management Fee",
    "  CAM",
    "Total Operating Expenses",
    "Net Operating Income",
    "Leasing Costs",
    "  Tenant Improvements",
    "  Leasing Commissions",
    "  Total Leasing Costs",
    "Capital Expenditures",
    "  Capital Reserves",
    "  Non-Leasing Capital Expense",
    "Total Capital Expenditures",
    "Total Leasing & Capital Costs",
    "Cash Flow Before Debt Service",
    "Cash Flow Available for Distribution",
)

# Full Argus cashflow block — 16 top-line + 18 lower = 34 rows.
ARGUS_CASHFLOW_ROWS: tuple[str, ...] = ARGUS_TOP_LINE_ROWS + ARGUS_CASHFLOW_LOWER_ROWS


def argus_top_line_income(
    result: "UnderwritingResult",
    prop: Property,
    frequency: str = "annual",
) -> pd.DataFrame:
    """Build the Argus "Cash Flow" top-line income block from an OpenVal run.

    Rows match Argus's row labels exactly (indent included) — the block runs
    from "Rental Revenue" down through "Effective Gross Revenue", 16 rows
    including three section headers (which come back as NaN).

    Columns: ``"Year 1" ... "Year N"`` fiscal years anchored on
    ``prop.acquisition_date`` (so a deal that closes in October has fiscal
    Y1 = Oct → next Sep), matching Argus's convention. ``frequency="monthly"``
    keeps the engine's monthly grain instead.

    Implementation notes:
      * **Potential Base Rent** is computed by re-projecting the rent roll
        with downtime / free rent zeroed and renewal probability pinned to
        1.0 — i.e. "what rent would we collect if every month were paid at
        the in-place schedule". This mirrors Argus's "PBR".
      * **Absorption & Turnover Vacancy** = actual gross_rent − PBR. The
        gap is negative whenever MLA downtime or pre-commencement vacancy
        suppresses the at-schedule rent.
      * **Free Rent** is read directly from ``free_rent_abatement``.
      * **Scheduled Base Rent** = ``gross_rent + free_rent_abatement``,
        which has been validated $-for-$ against Argus on a stabilized
        deal (see ``validation/argus_unbound_compare.py``).
    """
    cf = result.cashflows
    if cf.empty:
        raise ValueError("UnderwritingResult.cashflows is empty")

    months = cf.index
    pbr_monthly = _potential_base_rent_monthly(prop, months)

    monthly = pd.DataFrame(index=months)
    monthly["Potential Base Rent"] = pbr_monthly
    monthly["Absorption & Turnover Vacancy"] = cf["gross_rent"] - pbr_monthly
    monthly["Free Rent"] = cf["free_rent_abatement"]
    monthly["Scheduled Base Rent"] = cf["gross_rent"] + cf["free_rent_abatement"]
    monthly["Total Rental Revenue"] = monthly["Scheduled Base Rent"]
    recoveries = cf["recoveries"] if "recoveries" in cf.columns else pd.Series(0.0, index=months)
    monthly["Total Expense Recoveries"] = recoveries
    monthly["Total Other Tenant Revenue"] = recoveries
    monthly["Total Tenant Revenue"] = monthly["Total Rental Revenue"] + recoveries
    monthly["Potential Gross Revenue"] = monthly["Total Tenant Revenue"]
    monthly["Vacancy Allowance"] = cf["general_vacancy"] if "general_vacancy" in cf.columns else 0.0
    monthly["Credit Loss"] = cf["credit_loss"] if "credit_loss" in cf.columns else 0.0
    monthly["Total Vacancy & Credit Loss"] = (
        monthly["Vacancy Allowance"] + monthly["Credit Loss"]
    )
    monthly["Effective Gross Revenue"] = cf["egi"] if "egi" in cf.columns else (
        monthly["Potential Gross Revenue"] + monthly["Total Vacancy & Credit Loss"]
    )

    # Reindex into the Argus row order, including section-header rows that
    # carry no values (NaN) — those are visual headers in Argus.
    body_to_argus = {
        "Potential Base Rent": "  Potential Base Rent",
        "Absorption & Turnover Vacancy": "  Absorption & Turnover Vacancy",
        "Free Rent": "  Free Rent",
        "Scheduled Base Rent": "  Scheduled Base Rent",
        "Total Rental Revenue": "Total Rental Revenue",
        "Total Expense Recoveries": "  Total Expense Recoveries",
        "Total Other Tenant Revenue": "Total Other Tenant Revenue",
        "Total Tenant Revenue": "Total Tenant Revenue",
        "Potential Gross Revenue": "Potential Gross Revenue",
        "Vacancy Allowance": "  Vacancy Allowance",
        "Credit Loss": "  Credit Loss",
        "Total Vacancy & Credit Loss": "Total Vacancy & Credit Loss",
        "Effective Gross Revenue": "Effective Gross Revenue",
    }
    monthly = monthly.rename(columns=body_to_argus)
    # Section headers as empty rows so the block matches Argus visually.
    for header in ("Rental Revenue", "Other Tenant Revenue", "Vacancy & Credit Loss"):
        monthly[header] = float("nan")
    out_monthly = monthly[list(ARGUS_TOP_LINE_ROWS)].T
    out_monthly.index.name = "line_item"

    if frequency == "monthly":
        return out_monthly

    if frequency != "annual":
        raise ValueError(f"frequency must be 'monthly' or 'annual', got {frequency!r}")

    return _annualize_acquisition_anchored(out_monthly, prop.acquisition_date)


def argus_cashflow_report(
    result: "UnderwritingResult",
    prop: Property,
    frequency: str = "annual",
) -> pd.DataFrame:
    """Build the full Argus "Cash Flow" report — top-line income + opex +
    leasing & capital costs + bottom-line cash flow.

    Rows follow Argus's exact layout (``ARGUS_CASHFLOW_ROWS``). Section
    headers and unsupported sub-rows return NaN. The top 16 rows match
    ``argus_top_line_income``; the lower 18 rows cover:

      Operating Expenses
        Real Estate Taxes / Insurance / Property Mgmt Fee / CAM    NaN*
      Total Operating Expenses                                     -opex
      Net Operating Income                                          noi
      Leasing Costs
        Tenant Improvements                                         -ti
        Leasing Commissions                                         -lc
        Total Leasing Costs                                         -(ti+lc)
      Capital Expenditures
        Capital Reserves                                            NaN*
        Non-Leasing Capital Expense                                 -capex
      Total Capital Expenditures                                    -capex
      Total Leasing & Capital Costs                                 -(ti+lc+capex)
      Cash Flow Before Debt Service                                 noi - (ti+lc+capex)
      Cash Flow Available for Distribution                          cfb_ds + debt_service

    Reversion / sale proceeds are deliberately excluded from the CFB DS
    and CFAD lines so the terminal year matches Argus's operating-only
    presentation. Sale numbers live on ``UnderwritingResult.reversion``.

    * Opex / capex sub-rows require ``Property.opex_categories`` and
      ``Property.capex_categories`` (Phase B schema additions).

    Sign convention: opex and capital costs come back **positive** (Argus
    presents costs as positive in the operating-expense and capital-cost
    sections). Use ``argus_top_line_income`` if you only need the income
    portion.
    """
    cf = result.cashflows
    if cf.empty:
        raise ValueError("UnderwritingResult.cashflows is empty")

    # Top-line block (income side, already validated to mirror Argus exactly
    # on a stabilized year).
    top = argus_top_line_income(result, prop, frequency="monthly")

    months = cf.index
    lower = pd.DataFrame(index=top.columns)

    # Argus shows opex / leasing / capital costs as positive values; the
    # engine stores them as negatives in the cashflow DataFrame.
    noi = cf["noi"] if "noi" in cf.columns else pd.Series(0.0, index=months)
    opex_pos = -cf["opex"] if "opex" in cf.columns else pd.Series(0.0, index=months)
    ti_pos = -cf["ti"] if "ti" in cf.columns else pd.Series(0.0, index=months)
    lc_pos = -cf["lc"] if "lc" in cf.columns else pd.Series(0.0, index=months)
    capex_pos = -cf["capex"] if "capex" in cf.columns else pd.Series(0.0, index=months)
    debt_service = (
        cf["debt_service"] if "debt_service" in cf.columns else pd.Series(0.0, index=months)
    )
    # Cash Flow Before Debt Service is the OPERATING cash flow — NOI net of
    # leasing & capital costs. Reversion / sale proceeds live in a separate
    # report (``UnderwritingResult.reversion``) and are deliberately excluded
    # here so the terminal year isn't polluted by the sale (which is how
    # Argus presents it).
    cfb_ds = noi - (ti_pos + lc_pos + capex_pos)
    cfad = cfb_ds + debt_service  # debt_service is already negative on the cf

    for header in ("Operating Expenses", "Leasing Costs", "Capital Expenditures"):
        lower[header] = float("nan")
    # Opex sub-categories: populate from ``Property.opex_categories`` when
    # supplied. Argus's four standard category labels are recognized; any
    # custom category names still sum into Total Operating Expenses but
    # don't get a dedicated Argus row.
    cats = prop.opex_categories or {}
    for argus_label, cat_name in (
        ("  Real Estate Taxes", "Real Estate Taxes"),
        ("  Insurance", "Insurance"),
        ("  Property Management Fee", "Property Management Fee"),
        ("  CAM", "CAM"),
    ):
        if cat_name in cats:
            lower[argus_label] = _opex_category_monthly(cats[cat_name], months).values
        else:
            lower[argus_label] = float("nan")
    lower["Total Operating Expenses"] = opex_pos.values
    lower["Net Operating Income"] = cf["noi"].values if "noi" in cf.columns else 0.0
    lower["  Tenant Improvements"] = ti_pos.values
    lower["  Leasing Commissions"] = lc_pos.values
    lower["  Total Leasing Costs"] = (ti_pos + lc_pos).values
    # Capex sub-categories: populate from ``Property.capex_categories``.
    # The two Argus standard labels are recognized; custom names still feed
    # the total but don't get a dedicated row. When categories are absent,
    # the full capex falls into "Non-Leasing Capital Expense" by default.
    capex_cats = prop.capex_categories or {}
    if "Capital Reserves" in capex_cats:
        lower["  Capital Reserves"] = _opex_category_monthly(
            capex_cats["Capital Reserves"], months
        ).values
    else:
        lower["  Capital Reserves"] = float("nan")
    if "Non-Leasing Capital Expense" in capex_cats:
        lower["  Non-Leasing Capital Expense"] = _opex_category_monthly(
            capex_cats["Non-Leasing Capital Expense"], months
        ).values
    elif capex_cats:
        # Categories supplied but no explicit "Non-Leasing Capital Expense" —
        # leave that sub-row blank (custom-named categories live in the total
        # only).
        lower["  Non-Leasing Capital Expense"] = float("nan")
    else:
        # No categories at all → default behavior: lump full capex under
        # Non-Leasing Capital Expense so single-bucket users still see it.
        lower["  Non-Leasing Capital Expense"] = capex_pos.values
    lower["Total Capital Expenditures"] = capex_pos.values
    lower["Total Leasing & Capital Costs"] = (ti_pos + lc_pos + capex_pos).values
    lower["Cash Flow Before Debt Service"] = cfb_ds.values
    lower["Cash Flow Available for Distribution"] = cfad.values

    lower_t = lower[list(ARGUS_CASHFLOW_LOWER_ROWS)].T
    lower_t.index.name = "line_item"
    lower_t.columns = top.columns  # both indexed by month

    full_monthly = pd.concat([top, lower_t])
    full_monthly.index.name = "line_item"

    if frequency == "monthly":
        return full_monthly

    if frequency != "annual":
        raise ValueError(f"frequency must be 'monthly' or 'annual', got {frequency!r}")

    return _annualize_acquisition_anchored(full_monthly, prop.acquisition_date)


def _opex_category_monthly(
    cat_schedule: dict[int, Decimal], months: pd.DatetimeIndex
) -> pd.Series:
    """Spread an annual opex category schedule evenly across the months.

    Matches how ``_annual_to_monthly`` in ``openval.dcf`` distributes
    ``opex_annual`` — divide each year's amount by 12 across that year's
    months — so category sub-rows always sum to the ``Total Operating
    Expenses`` line within rounding.
    """
    vals = [float(cat_schedule.get(ts.year, 0)) / 12.0 for ts in months]
    return pd.Series(vals, index=months)


def _potential_base_rent_monthly(prop: Property, months: pd.DatetimeIndex) -> pd.Series:
    """Project the rent roll's "at-schedule" potential rent each month.

    Mirrors Argus's "Potential Base Rent" line: the gross rent if every
    month of the projection were collected at the lease's in-place schedule
    (no pre-commencement vacancy, no MLA downtime, no free rent abatement,
    deterministic renewal at scheduled escalations).

    Mechanics: shift each non-vacant-placeholder lease's commencement
    backwards to ``acquisition_date`` so the engine evaluates the lease's
    rent step from day 1; zero out free-rent / downtime / probabilistic
    rollover on its MLA copy; re-run ``project_rent_roll`` and take the
    resulting ``base_rent`` series.
    """
    acq = prop.acquisition_date
    perfect_leases: list[Lease] = []
    for lease in prop.leases:
        mla = lease.market_leasing_assumption
        perfect_mla = None
        if mla is not None:
            # Zero ``renewal_market_discount_pct`` too. With
            # renewal_probability=1.0 the MLA spawns a renewal segment after
            # the parent lease ends; without this knob, that segment would
            # carry the lease-up haircut and PBR would understate Argus's
            # at-market convention. Argus's PBR always uses the full
            # at-market new-tenant rate.
            perfect_mla = mla.model_copy(
                update={
                    "downtime_months_new": 0,
                    "free_rent_months_new": 0,
                    "free_rent_months_renewal": 0,
                    "renewal_probability": Decimal("1.0"),
                    "renewal_market_discount_pct": Decimal("0"),
                }
            )

        new_start = lease.start_date
        new_steps = list(lease.base_rent_steps)
        # Shift the lease's commencement back to acquisition so PBR captures
        # the full projection window at the in-place rate. Skip the special
        # placeholder lease used for "vacant at acquisition" (its $0 PSF is
        # supposed to delegate to MLA spawn from day 1, which the perfect
        # MLA above already handles).
        if lease.start_date > acq and lease.tenant_name != "VACANT":
            new_start = acq
            new_steps = [s for s in new_steps if s.start_date > acq]
            first_psf = lease.base_rent_steps[0].annual_psf
            new_steps.insert(0, RentStep(start_date=acq, annual_psf=first_psf))

        perfect_leases.append(
            lease.model_copy(
                update={
                    "start_date": new_start,
                    "base_rent_steps": new_steps,
                    "free_rent_months": 0,
                    "market_leasing_assumption": perfect_mla,
                }
            )
        )

    start = months[0].date()
    end_month_start = months[-1].date()
    rr = project_rent_roll(perfect_leases, start, end_month_start, cpi_series=prop.cpi_series)
    return rr["base_rent"].reindex(months).fillna(0.0)


def _annualize_acquisition_anchored(monthly: pd.DataFrame, acquisition: date) -> pd.DataFrame:
    """Sum monthly columns into fiscal years anchored at ``acquisition``.

    Trailing stub months (if the cashflow window isn't a clean 12-multiple)
    fall into a final ``"Year N (stub Xmo)"`` bucket so no rent is dropped.
    """
    n_months = monthly.shape[1]
    n_years = n_months // 12
    out: dict[str, pd.Series] = {}
    for y in range(n_years):
        slc = monthly.iloc[:, y * 12 : (y + 1) * 12]
        out[f"Year {y + 1}"] = slc.sum(axis=1, min_count=1)
    remainder = n_months - n_years * 12
    if remainder:
        stub = monthly.iloc[:, n_years * 12 :]
        out[f"Year {n_years + 1} (stub {remainder}mo)"] = stub.sum(axis=1, min_count=1)
    df = pd.DataFrame(out, index=monthly.index)
    df.index.name = "line_item"
    return df
