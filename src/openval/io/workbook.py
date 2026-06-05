"""Read an OpenVal sample-workbook-shaped ``.xlsx`` into a ``Property``.

The workbook format is the one produced by
``scripts/build_sample_workbook.py``: each Argus-style assumption category
on its own sheet (property / timing / purchase / debt / vacancy_credit /
opex / capex / cpi / leases / rent_steps / mla / refinance).

This module exposes a single entry point — ``read_property_workbook`` —
shared between ``scripts/run_workbook.py`` (which also writes outputs
back into the file) and the web API ``web/api/parse_workbook.py`` (which
accepts uploads and returns the JSON Property).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from openval import (
    ExpenseStructure,
    Loan,
    MarketLeasingAssumption,
    Property,
    Refinance,
)
from openval.io.rent_roll import read_rent_roll_excel
from openval.lease import Lease


# ----------------------------------------------------------------------
# Sheet readers (private — collated into ``read_property_workbook`` below)
# ----------------------------------------------------------------------


def _read_kv(path: Path, sheet: str) -> dict:
    try:
        df = pd.read_excel(path, sheet_name=sheet, dtype=object)
    except (ValueError, KeyError):
        return {}
    df.columns = [c.strip().lower() for c in df.columns]
    return {
        str(row["field"]).strip(): row["value"]
        for _, row in df.iterrows()
        if pd.notna(row["field"])
    }


def _read_opex(path: Path) -> dict[int, Decimal]:
    df = pd.read_excel(path, sheet_name="opex", dtype=object)
    return {int(r["year"]): Decimal(str(r["annual_opex"])) for _, r in df.iterrows()}


def _read_capex(path: Path) -> dict[int, Decimal]:
    try:
        df = pd.read_excel(path, sheet_name="capex", dtype=object)
    except (ValueError, KeyError):
        return {}
    return {int(r["year"]): Decimal(str(r["annual_capex"])) for _, r in df.iterrows()}


def _read_cpi(path: Path) -> dict[int, Decimal]:
    try:
        df = pd.read_excel(path, sheet_name="cpi", dtype=object)
    except (ValueError, KeyError):
        return {}
    return {
        int(r["year"]): Decimal(str(r["cpi_rate"]))
        for _, r in df.iterrows()
        if pd.notna(r["cpi_rate"])
    }


def _read_mla(path: Path) -> dict[str, MarketLeasingAssumption]:
    try:
        df = pd.read_excel(path, sheet_name="mla", dtype=object)
    except (ValueError, KeyError):
        return {}
    out: dict[str, MarketLeasingAssumption] = {}
    for _, r in df.iterrows():
        out[str(r["suite_id"])] = MarketLeasingAssumption(
            market_rent_psf=Decimal(str(r["market_rent_psf"])),
            market_rent_growth_pct=Decimal(str(r["market_rent_growth_pct"])),
            new_term_months=int(r["new_term_months"]),
            rent_escalation_pct=Decimal(str(r["rent_escalation_pct"])),
            free_rent_months_new=int(r["free_rent_months_new"]),
            free_rent_months_renewal=int(r["free_rent_months_renewal"]),
            ti_psf_new=Decimal(str(r["ti_psf_new"])),
            ti_psf_renewal=Decimal(str(r["ti_psf_renewal"])),
            lc_pct_new=Decimal(str(r["lc_pct_new"])),
            lc_pct_renewal=Decimal(str(r["lc_pct_renewal"])),
            renewal_probability=Decimal(str(r["renewal_probability"])),
            downtime_months_new=int(r["downtime_months_new"]),
            renewal_market_discount_pct=Decimal(str(r["renewal_market_discount_pct"])),
            expense_structure=ExpenseStructure(str(r["expense_structure"]).strip().upper()),
        )
    return out


def _coerce_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    return v


def _read_refinance(path: Path) -> Optional[Refinance]:
    kv = _read_kv(path, "refinance")
    if not kv:
        return None
    raw_date = kv.get("refi_effective_date")
    if raw_date is None or (isinstance(raw_date, float) and pd.isna(raw_date)):
        return None
    return Refinance(
        effective_date=_coerce_date(raw_date),
        new_loan=Loan(
            principal=Decimal(str(kv["refi_new_principal"])),
            rate_annual=Decimal(str(kv["refi_new_rate_annual"])),
            amortization_years=int(kv["refi_new_amortization_years"]),
            term_years=int(kv["refi_new_term_years"]),
            interest_only_years=int(kv.get("refi_new_interest_only_years") or 0),
        ),
        prepayment_penalty_pct=Decimal(str(kv.get("refi_prepayment_penalty_pct", "0"))),
    )


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def write_property_workbook(prop: Property, dest: Union[str, Path]) -> Path:
    """Serialize a ``Property`` into the canonical OpenVal workbook layout.

    Produces the same sheet structure that
    ``scripts/build_sample_workbook.py`` emits, so the output round-trips
    cleanly through ``read_property_workbook`` (and through
    ``scripts/run_workbook.py``, which also writes its output sheets back
    into the same file).
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        for name, df in _build_sheets(prop).items():
            df.to_excel(writer, sheet_name=name, index=False)
    return dest


def _build_sheets(prop: Property) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}

    sheets["property"] = _kv_sheet([
        ("name", prop.name),
        ("rentable_sf", prop.rentable_sf),
    ])
    sheets["timing"] = _kv_sheet([
        ("acquisition_date", prop.acquisition_date.isoformat()),
        ("hold_years", prop.hold_years),
        ("reversion_basis", prop.reversion_basis),
    ])
    sheets["purchase"] = _kv_sheet([
        ("acquisition_price", str(prop.acquisition_price)),
        ("acquisition_costs_pct", str(prop.acquisition_costs_pct)),
        ("sale_costs_pct", str(prop.sale_costs_pct)),
        ("exit_cap_rate", str(prop.exit_cap_rate)),
    ])
    if prop.loan is not None:
        sheets["debt"] = _kv_sheet([
            ("loan_principal", str(prop.loan.principal)),
            ("loan_rate_annual", str(prop.loan.rate_annual)),
            ("loan_amortization_years", prop.loan.amortization_years),
            ("loan_term_years", prop.loan.term_years),
            ("loan_interest_only_years", prop.loan.interest_only_years),
        ])
    if prop.refinance is not None:
        ref = prop.refinance
        sheets["refinance"] = _kv_sheet([
            ("refi_effective_date", ref.effective_date.isoformat()),
            ("refi_new_principal", str(ref.new_loan.principal)),
            ("refi_new_rate_annual", str(ref.new_loan.rate_annual)),
            ("refi_new_amortization_years", ref.new_loan.amortization_years),
            ("refi_new_term_years", ref.new_loan.term_years),
            ("refi_new_interest_only_years", ref.new_loan.interest_only_years),
            ("refi_prepayment_penalty_pct", str(ref.prepayment_penalty_pct)),
        ])
    sheets["vacancy_credit"] = _kv_sheet([
        ("general_vacancy_pct", str(prop.general_vacancy_pct)),
        ("credit_loss_pct", str(prop.credit_loss_pct)),
        ("opex_non_recoverable_pct", str(prop.opex_non_recoverable_pct)),
        (
            "opex_gross_up_at_occupancy_pct",
            str(prop.opex_gross_up_at_occupancy_pct)
            if prop.opex_gross_up_at_occupancy_pct is not None
            else "",
        ),
    ])
    sheets["cpi"] = pd.DataFrame(
        [{"year": y, "cpi_rate": str(v)} for y, v in sorted(prop.cpi_series.items())]
    )
    sheets["opex"] = pd.DataFrame(
        [{"year": y, "annual_opex": str(v)} for y, v in sorted(prop.opex_annual.items())]
    )
    sheets["capex"] = pd.DataFrame(
        [{"year": y, "annual_capex": str(v)} for y, v in sorted(prop.capex_annual.items())]
    )
    sheets["leases"] = pd.DataFrame(
        [_lease_row(l) for l in prop.leases]
    )
    sheets["rent_steps"] = pd.DataFrame(
        _all_rent_steps(prop.leases)
    )
    sheets["mla"] = pd.DataFrame(
        [_mla_row(l) for l in prop.leases if l.market_leasing_assumption is not None]
    )

    return sheets


def _kv_sheet(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["field", "value"])


def _lease_row(lease: Lease) -> dict:
    return {
        "suite_id": lease.suite_id,
        "tenant_name": lease.tenant_name,
        "area_sf": lease.area_sf,
        "start_date": lease.start_date.isoformat(),
        "end_date": lease.end_date.isoformat(),
        # base_rent_psf seeds the rent roll reader if rent_steps is empty;
        # use the first step as the seed value.
        "base_rent_psf": float(lease.base_rent_steps[0].annual_psf),
        "expense_structure": lease.expense_structure.value,
        "free_rent_months": lease.free_rent_months,
        "ti_psf": float(lease.ti_psf),
        "lc_pct_first_year_rent": float(lease.lc_pct_first_year_rent),
    }


def _all_rent_steps(leases: list[Lease]) -> list[dict]:
    rows = []
    for lease in leases:
        for step in lease.base_rent_steps:
            rows.append({
                "suite_id": lease.suite_id,
                "start_date": step.start_date.isoformat(),
                "annual_psf": float(step.annual_psf),
            })
    return rows


def _mla_row(lease: Lease) -> dict:
    mla = lease.market_leasing_assumption
    assert mla is not None
    return {
        "suite_id": lease.suite_id,
        "market_rent_psf": float(mla.market_rent_psf),
        "market_rent_growth_pct": float(mla.market_rent_growth_pct),
        "new_term_months": mla.new_term_months,
        "rent_escalation_pct": float(mla.rent_escalation_pct),
        "free_rent_months_new": mla.free_rent_months_new,
        "free_rent_months_renewal": mla.free_rent_months_renewal,
        "ti_psf_new": float(mla.ti_psf_new),
        "ti_psf_renewal": float(mla.ti_psf_renewal),
        "lc_pct_new": float(mla.lc_pct_new),
        "lc_pct_renewal": float(mla.lc_pct_renewal),
        "renewal_probability": float(mla.renewal_probability),
        "downtime_months_new": mla.downtime_months_new,
        "renewal_market_discount_pct": float(mla.renewal_market_discount_pct),
        "expense_structure": mla.expense_structure.value,
    }


def read_property_workbook(source: Union[str, Path]) -> Property:
    """Parse an OpenVal sample-workbook-shaped ``.xlsx`` into a ``Property``.

    The waterfall sheet (if present) isn't consumed here — it's not part
    of ``Property``. The caller (``scripts/run_workbook.py``) reads it
    separately.

    Accepts a path; the web upload endpoint writes bytes to a temp file
    first and passes the path here.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")

    prop_kv = _read_kv(path, "property")
    timing_kv = _read_kv(path, "timing")
    purchase_kv = _read_kv(path, "purchase")
    debt_kv = _read_kv(path, "debt")
    vac_kv = _read_kv(path, "vacancy_credit")

    leases = read_rent_roll_excel(path, leases_sheet="leases", rent_steps_sheet="rent_steps")
    mlas = _read_mla(path)
    if mlas:
        leases = [
            l.model_copy(update={"market_leasing_assumption": mlas[l.suite_id]})
            if l.suite_id in mlas
            else l
            for l in leases
        ]

    loan: Optional[Loan] = None
    if debt_kv.get("loan_principal"):
        loan = Loan(
            principal=Decimal(str(debt_kv["loan_principal"])),
            rate_annual=Decimal(str(debt_kv["loan_rate_annual"])),
            amortization_years=int(debt_kv["loan_amortization_years"]),
            term_years=int(debt_kv["loan_term_years"]),
            interest_only_years=int(debt_kv.get("loan_interest_only_years") or 0),
        )

    refinance = _read_refinance(path)
    cpi = _read_cpi(path)

    return Property(
        name=str(prop_kv["name"]),
        rentable_sf=int(prop_kv["rentable_sf"]),
        leases=leases,
        opex_annual=_read_opex(path),
        capex_annual=_read_capex(path),
        acquisition_date=_coerce_date(timing_kv["acquisition_date"]),
        acquisition_price=Decimal(str(purchase_kv["acquisition_price"])),
        acquisition_costs_pct=Decimal(str(purchase_kv.get("acquisition_costs_pct", "0"))),
        hold_years=int(timing_kv["hold_years"]),
        exit_cap_rate=Decimal(str(purchase_kv["exit_cap_rate"])),
        sale_costs_pct=Decimal(str(purchase_kv.get("sale_costs_pct", "0.02"))),
        reversion_basis=str(timing_kv.get("reversion_basis", "trailing")).strip().lower(),
        general_vacancy_pct=Decimal(str(vac_kv.get("general_vacancy_pct", "0"))),
        credit_loss_pct=Decimal(str(vac_kv.get("credit_loss_pct", "0"))),
        opex_non_recoverable_pct=Decimal(str(vac_kv.get("opex_non_recoverable_pct", "0"))),
        opex_gross_up_at_occupancy_pct=(
            Decimal(str(vac_kv["opex_gross_up_at_occupancy_pct"]))
            if vac_kv.get("opex_gross_up_at_occupancy_pct") not in (None, "")
            else None
        ),
        cpi_series=cpi,
        loan=loan,
        refinance=refinance,
    )
