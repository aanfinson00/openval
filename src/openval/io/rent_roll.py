"""Generic rent-roll importer for ``.xlsx`` (and ``.csv``) workbooks.

The expected layout is one row per lease in a ``leases`` sheet (or a single
CSV file), with optional escalation steps in a ``rent_steps`` sheet.

leases sheet columns
====================

Required:
    suite_id            str    unique lease identifier
    tenant_name         str
    area_sf             int    > 0
    start_date          date   commencement
    end_date            date   strictly after start_date
    base_rent_psf       Decimal  initial $/sf/year — becomes a step at
                                   start_date if no rent_steps row exists
    expense_structure   str    one of NNN / MG / FSG

Conditional:
    base_year           int    required for MG when expense_stop_psf is blank
    expense_stop_psf    Decimal  alt to base_year for MG

Optional (defaults shown):
    free_rent_months           int     default 0
    ti_psf                     Decimal default 0
    lc_pct_first_year_rent     Decimal default 0
    recovery_cap_pct           Decimal default None (no cap)

rent_steps sheet columns (optional, second sheet)
=================================================
    suite_id            str    must match a row in leases
    start_date          date   step takes effect
    annual_psf          Decimal

If both ``base_rent_psf`` and explicit rent_steps exist for a suite, the
explicit steps are used; ``base_rent_psf`` is treated as the first step
(prepended if no step at start_date exists, ignored if one does).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional, Union

import pandas as pd

from openval.lease import ExpenseStructure, Lease, RentStep


_REQUIRED_LEASE_COLUMNS = {
    "suite_id",
    "tenant_name",
    "area_sf",
    "start_date",
    "end_date",
    "expense_structure",
}

_OPTIONAL_LEASE_COLUMNS = {
    "base_rent_psf",
    "base_year",
    "expense_stop_psf",
    "free_rent_months",
    "ti_psf",
    "lc_pct_first_year_rent",
    "recovery_cap_pct",
}


def read_rent_roll_excel(
    path: Union[str, Path],
    leases_sheet: str = "leases",
    rent_steps_sheet: str = "rent_steps",
) -> list[Lease]:
    """Read a rent roll workbook and return a list of ``Lease`` models.

    ``rent_steps`` sheet is optional. If missing, every lease uses a single
    step from ``base_rent_psf``.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rent roll file not found: {path}")

    leases_df = pd.read_excel(path, sheet_name=leases_sheet, dtype=object)
    leases_df = _normalize_columns(leases_df)
    _validate_leases_columns(leases_df)

    rent_steps_df: Optional[pd.DataFrame] = None
    try:
        rent_steps_df = pd.read_excel(path, sheet_name=rent_steps_sheet, dtype=object)
        rent_steps_df = _normalize_columns(rent_steps_df)
        _validate_rent_steps_columns(rent_steps_df)
    except (ValueError, KeyError):
        rent_steps_df = None

    return _build_leases(leases_df, rent_steps_df)


def read_rent_roll_csv(path: Union[str, Path]) -> list[Lease]:
    """Read a single CSV with one lease per row.

    CSV mode does not support a separate rent_steps file; every lease uses
    a single step from ``base_rent_psf``. Multi-step leases need the Excel
    importer.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rent roll file not found: {path}")

    df = pd.read_csv(path, dtype=object)
    df = _normalize_columns(df)
    _validate_leases_columns(df)
    return _build_leases(df, rent_steps_df=None)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _validate_leases_columns(df: pd.DataFrame) -> None:
    missing = _REQUIRED_LEASE_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"rent roll missing required columns: {sorted(missing)}; "
            f"got: {sorted(df.columns)}"
        )


def _validate_rent_steps_columns(df: pd.DataFrame) -> None:
    required = {"suite_id", "start_date", "annual_psf"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"rent_steps sheet missing required columns: {sorted(missing)}"
        )


def _build_leases(
    leases_df: pd.DataFrame, rent_steps_df: Optional[pd.DataFrame]
) -> list[Lease]:
    steps_by_suite: dict[str, list[RentStep]] = {}
    if rent_steps_df is not None:
        for _, row in rent_steps_df.iterrows():
            suite = str(row["suite_id"])
            steps_by_suite.setdefault(suite, []).append(
                RentStep(
                    start_date=_to_date(row["start_date"]),
                    annual_psf=_to_decimal(row["annual_psf"]),
                )
            )
        for s in steps_by_suite.values():
            s.sort(key=lambda x: x.start_date)

    leases: list[Lease] = []
    for _, row in leases_df.iterrows():
        suite_id = str(row["suite_id"])
        start = _to_date(row["start_date"])
        end = _to_date(row["end_date"])

        base_psf = _to_decimal_optional(row.get("base_rent_psf"))
        steps = list(steps_by_suite.get(suite_id, []))
        if base_psf is not None and (not steps or steps[0].start_date > start):
            steps.insert(0, RentStep(start_date=start, annual_psf=base_psf))
        if not steps:
            raise ValueError(
                f"lease {suite_id} has no base_rent_psf and no rent_steps rows"
            )

        expense_structure = ExpenseStructure(str(row["expense_structure"]).strip().upper())

        leases.append(
            Lease(
                suite_id=suite_id,
                tenant_name=str(row["tenant_name"]),
                area_sf=int(row["area_sf"]),
                start_date=start,
                end_date=end,
                base_rent_steps=steps,
                free_rent_months=_to_int_default(row.get("free_rent_months"), 0),
                ti_psf=_to_decimal_default(row.get("ti_psf"), Decimal("0")),
                lc_pct_first_year_rent=_to_decimal_default(
                    row.get("lc_pct_first_year_rent"), Decimal("0")
                ),
                expense_structure=expense_structure,
                base_year=_to_int_optional(row.get("base_year")),
                expense_stop_psf=_to_decimal_optional(row.get("expense_stop_psf")),
                recovery_cap_pct=_to_decimal_optional(row.get("recovery_cap_pct")),
            )
        )

    return leases


def _to_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    if isinstance(v, pd.Timestamp):
        return v.date()
    raise ValueError(f"cannot coerce {v!r} to date")


def _to_decimal(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None or (isinstance(v, float) and pd.isna(v)):
        raise ValueError("expected Decimal, got None/NaN")
    return Decimal(str(v))


def _to_decimal_optional(v) -> Optional[Decimal]:
    if v is None or _isna(v):
        return None
    return Decimal(str(v))


def _to_decimal_default(v, default: Decimal) -> Decimal:
    if v is None or _isna(v):
        return default
    return Decimal(str(v))


def _to_int_optional(v) -> Optional[int]:
    if v is None or _isna(v):
        return None
    return int(v)


def _to_int_default(v, default: int) -> int:
    if v is None or _isna(v):
        return default
    return int(v)


def _isna(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False
