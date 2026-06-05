"""Argus Enterprise cashflow ``.xls`` reader.

Argus's "Cash Flow" report exports a single-sheet binary ``.xls`` workbook with
a fixed top-line income schema (verified across multiple deals). This module
parses the report into a normalized DataFrame while preserving Argus's exact
row labels (indent included) so downstream consumers can mirror the report
1:1.

Layout (column 0 = label, then one column per month, then a ``"Total"`` col):

    row  0 — blank
    row  1 — "Cash Flow"
    row  2 — "<Property Name> (Amounts in <CCY>)"
    row  3 — "<MMM, YYYY> through <MMM, YYYY>"
    row  4 — generation timestamp (e.g. "6/1/2026 11:10:29 AM")
    row  6 — "Forecast" labels per column
    row  8 — "Month 1" ... "Month N"
    row  9 — "<MMM>-YYYY" per column, then "Total"
    row 11+— labelled data rows (section headers have no values)

The top-line income block (down through Effective Gross Revenue) is identical
across all observed exports; opex/capex line items vary by deal. This loader
keeps every label found, so the full Argus row set survives the round-trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import ClassVar, Optional, Union

import pandas as pd
import xlrd


# Argus emits a fixed set of top-line income rows in this exact order across
# every export we have seen. Tuple values include the two-space indent that
# Argus uses for child line items — preserving the indent lets callers render
# the rollup hierarchy without re-deriving it.
TOP_LINE_INCOME_ROWS: tuple[str, ...] = (
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


@dataclass(frozen=True)
class ArgusCashflow:
    """Normalized representation of an Argus Cash Flow ``.xls`` export."""

    property_name: str
    currency: str
    period_start: date
    period_end: date
    generated_at: Optional[datetime]
    monthly: pd.DataFrame
    total: pd.Series

    TOP_LINE_INCOME_ROWS: ClassVar[tuple[str, ...]] = TOP_LINE_INCOME_ROWS

    def top_line_income(self, frequency: str = "monthly") -> pd.DataFrame:
        """Return only the top-line income rows (down through EGR).

        ``frequency``: ``"monthly"`` keeps Argus's native monthly grain;
        ``"annual"`` rolls the 132 months into fiscal years anchored to
        ``period_start`` (so Year 1 spans the first 12 months of the report,
        matching Argus's own annualized view).
        """
        rows = [r for r in TOP_LINE_INCOME_ROWS if r in self.monthly.index]
        df = self.monthly.loc[rows]
        if frequency == "monthly":
            return df.copy()
        if frequency == "annual":
            return _annualize(df, self.period_start)
        raise ValueError(f"frequency must be 'monthly' or 'annual', got {frequency!r}")


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def read_argus_cashflow_xls(path: Union[str, Path]) -> ArgusCashflow:
    """Parse an Argus Cash Flow ``.xls`` export into an ``ArgusCashflow``."""
    path = Path(path)
    wb = xlrd.open_workbook(str(path))
    sh = wb.sheet_by_index(0)

    property_name, currency = _parse_property_header(sh.cell_value(2, 0))
    period_start, period_end = _parse_period(sh.cell_value(3, 0))
    generated_at = _parse_generated_at(sh.cell_value(4, 0))

    # Column 0 = labels; the last column with a non-blank header on row 9 is
    # the "Total" column. Everything in between (cols 1..N-1) is monthly.
    date_header = [sh.cell_value(9, c) for c in range(sh.ncols)]
    month_cols: list[int] = []
    month_dates: list[date] = []
    total_col: Optional[int] = None
    for c in range(1, sh.ncols):
        hdr = str(date_header[c]).strip()
        if not hdr:
            continue
        if hdr.lower() == "total":
            total_col = c
            continue
        month_dates.append(_parse_month_header(hdr))
        month_cols.append(c)

    # Walk every labelled row; preserve label text exactly (indent included).
    labels: list[str] = []
    monthly_data: list[list[float]] = []
    totals: list[float] = []
    for r in range(11, sh.nrows):
        label = sh.cell_value(r, 0)
        if not isinstance(label, str):
            continue
        # Argus pads labels with trailing spaces in some exports; right-strip
        # only, never left-strip — the leading indent is the hierarchy signal.
        label = label.rstrip()
        if not label:
            continue
        labels.append(label)
        monthly_data.append([_cell_to_float(sh.cell_value(r, c)) for c in month_cols])
        totals.append(
            _cell_to_float(sh.cell_value(r, total_col)) if total_col is not None else float("nan")
        )

    month_index = pd.DatetimeIndex([pd.Timestamp(d) for d in month_dates], name="month")
    monthly = pd.DataFrame(monthly_data, index=pd.Index(labels, name="line_item"), columns=month_index)
    total = pd.Series(totals, index=pd.Index(labels, name="line_item"), name="argus_total")

    return ArgusCashflow(
        property_name=property_name,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        monthly=monthly,
        total=total,
    )


# ----------------------------------------------------------------------
# Header parsing helpers
# ----------------------------------------------------------------------


_PROPERTY_HEADER_RE = re.compile(r"^(?P<name>.+?)\s*\(Amounts in (?P<ccy>[A-Z]{3})\)\s*$")
_PERIOD_RE = re.compile(
    r"^(?P<m1>[A-Za-z]{3}),\s*(?P<y1>\d{4})\s+through\s+(?P<m2>[A-Za-z]{3}),\s*(?P<y2>\d{4})\s*$"
)


def _parse_property_header(cell: object) -> tuple[str, str]:
    s = str(cell).strip()
    m = _PROPERTY_HEADER_RE.match(s)
    if not m:
        # Be lenient: if Argus ever drops the currency suffix, keep the whole
        # string as the property name and default to USD.
        return s, "USD"
    return m.group("name").strip(), m.group("ccy")


def _parse_period(cell: object) -> tuple[date, date]:
    s = str(cell).strip()
    m = _PERIOD_RE.match(s)
    if not m:
        raise ValueError(f"Could not parse Argus period header: {s!r}")
    start = datetime.strptime(f"{m['m1']} {m['y1']}", "%b %Y").date().replace(day=1)
    end_first = datetime.strptime(f"{m['m2']} {m['y2']}", "%b %Y").date().replace(day=1)
    # End of period = last day of the last month.
    end = (pd.Timestamp(end_first) + pd.offsets.MonthEnd(0)).date()
    return start, end


def _parse_generated_at(cell: object) -> Optional[datetime]:
    s = str(cell).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_month_header(s: str) -> date:
    return datetime.strptime(s.strip(), "%b-%Y").date().replace(day=1)


def _cell_to_float(v: object) -> float:
    if v is None or v == "":
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ----------------------------------------------------------------------
# Annualization
# ----------------------------------------------------------------------


def _annualize(monthly: pd.DataFrame, period_start: date) -> pd.DataFrame:
    """Sum 12 columns at a time starting at ``period_start``.

    Year labels follow Argus's convention: ``"Year 1"``, ``"Year 2"``, ... so
    callers can join against the rest of the engine's annual outputs.
    """
    n_cols = monthly.shape[1]
    n_years = n_cols // 12
    cols = monthly.columns
    out = {}
    for y in range(n_years):
        slc = monthly.iloc[:, y * 12 : (y + 1) * 12]
        # Sum across columns; sections-only rows (all NaN) stay NaN.
        out[f"Year {y + 1}"] = slc.sum(axis=1, min_count=1)
    # Trailing stub months (if not a clean multiple of 12) keep their own bucket.
    remainder = n_cols - n_years * 12
    if remainder:
        stub = monthly.iloc[:, n_years * 12 :]
        out[f"Year {n_years + 1} (stub {remainder}mo)"] = stub.sum(axis=1, min_count=1)
    return pd.DataFrame(out, index=monthly.index)
