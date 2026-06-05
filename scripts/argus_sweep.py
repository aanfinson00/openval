"""Sweep all 5 Argus cashflow fixtures and characterize where OpenVal
matches Argus and where it doesn't.

For each deal:
  1. Load the Argus fixture and detect its shape (stabilized vs. lease-up
     at acquisition, presence and timing of A&T vacancy / free rent
     rollovers, vacancy allowance / credit loss profile).
  2. If a matching OpenVal stub is registered, compute per-row drift for
     the full Argus cashflow block over Y1..Y10.
  3. Print a deal-by-deal summary, then a global gap list.

Run: ``.venv/bin/python scripts/argus_sweep.py``

Output is also persisted to ``docs/ARGUS_SWEEP.md`` as the canonical
characterization doc, so the engine team can plan future schema lifts
from a stable reference.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "validation"))

from openval import argus_cashflow_report, project_property  # noqa: E402
from openval.io import read_argus_cashflow_xls  # noqa: E402
from openval.reporting import ARGUS_CASHFLOW_ROWS  # noqa: E402


FIXTURE_DIR = ROOT / "validation" / "fixtures" / "argus_cashflow"


# Registered stubs: filename → builder. Easy to extend as more stubs land.
STUBS: dict[str, str] = {
    "Unbound Gateway - Phase I": "argus_unbound",
    "Telephone Road": "argus_telephone_road",
}


def _annualize_monthly(monthly: pd.DataFrame, n_years: int) -> pd.DataFrame:
    return pd.concat(
        [
            monthly.iloc[:, y * 12 : (y + 1) * 12].sum(axis=1, min_count=1)
            for y in range(n_years)
        ],
        axis=1,
        keys=[f"Year {i + 1}" for i in range(n_years)],
    )


def _shape_signature(ann: pd.DataFrame) -> dict[str, object]:
    """Boil an Argus deal down to a small set of shape descriptors that
    explain why our engine matches or doesn't match it.
    """

    def _nonzero_years(row: str) -> list[int]:
        if row not in ann.index:
            return []
        # Some Argus exports re-use a label (e.g. period header repeats). If
        # ann.loc[row] returns a DataFrame, collapse to the first occurrence.
        series = ann.loc[row]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[0]
        return [int(c.split()[-1]) for c, v in series.items() if pd.notna(v) and abs(float(v)) > 0.5]

    return {
        "Y1 A&T vacancy?":      bool(ann.loc["  Absorption & Turnover Vacancy", "Year 1"]),
        "Y1 free rent?":        bool(ann.loc["  Free Rent", "Year 1"]),
        "Mid-hold A&T years":   _nonzero_years("  Absorption & Turnover Vacancy"),
        "Mid-hold free rent years": _nonzero_years("  Free Rent"),
        "Vacancy allowance":    "constant" if _has_constant_pct(ann, "  Vacancy Allowance") else (
                                    "varies year-to-year" if _nonzero_years("  Vacancy Allowance") else "zero"
                                ),
        "Credit loss":          "constant" if _has_constant_pct(ann, "  Credit Loss") else (
                                    "varies year-to-year" if _nonzero_years("  Credit Loss") else "zero"
                                ),
        "Mid-hold TI/LC years": _nonzero_years("  Tenant Improvements") + _nonzero_years("  Leasing Commissions"),
        "Capital Reserves recurring?": len(_nonzero_years("  Capital Reserves")) >= 5,
    }


def _has_constant_pct(ann: pd.DataFrame, row: str) -> bool:
    """Is this row a constant % of Scheduled Base Rent (within 10bps)?"""
    if row not in ann.index:
        return False
    row_series = ann.loc[row]
    sbr_series = ann.loc["  Scheduled Base Rent"]
    if isinstance(row_series, pd.DataFrame):
        row_series = row_series.iloc[0]
    if isinstance(sbr_series, pd.DataFrame):
        sbr_series = sbr_series.iloc[0]
    pcts = []
    for col in ann.columns[:10]:
        v = row_series[col]
        sbr = sbr_series[col]
        if pd.isna(v) or pd.isna(sbr) or float(sbr) <= 0 or float(v) == 0:
            return False
        pcts.append(abs(float(v)) / float(sbr))
    if len(pcts) < 2:
        return False
    spread = max(pcts) - min(pcts)
    return spread < 0.001


def _build_openval_for(fixture_path: Path, stub_module: str | None) -> pd.DataFrame | None:
    if stub_module is None:
        return None
    mod = __import__(stub_module)
    prop = mod.build_stub_property()
    result = project_property(prop)
    return argus_cashflow_report(result, prop)


def _drift_summary(argus: pd.DataFrame, openval: pd.DataFrame) -> pd.DataFrame:
    n = min(10, argus.shape[1], openval.shape[1])
    a = argus.iloc[:, :n]
    o = openval.iloc[:, :n]
    o.columns = a.columns
    d = (o - a).abs()
    # Per-row: max abs drift across Y1..Y10
    rows = []
    for row in ARGUS_CASHFLOW_ROWS:
        if row not in d.index:
            continue
        max_d = d.loc[row].max()
        if pd.isna(max_d):
            continue
        if max_d < 25:
            tag = "✓ within $25"
        elif max_d < 1000:
            tag = f"~ within $1K (max ${max_d:,.0f})"
        else:
            tag = f"✗ drift ${max_d:,.0f}"
        rows.append({"row": row.strip(), "max_abs_drift": float(max_d), "verdict": tag})
    return pd.DataFrame(rows)


def main() -> None:
    fixtures = sorted(glob.glob(str(FIXTURE_DIR / "*_Cash Flow_*.xls")))
    if not fixtures:
        sys.exit(f"No Argus fixtures found under {FIXTURE_DIR}")

    md_lines: list[str] = []
    md_lines.append("# Argus 5-deal sweep")
    md_lines.append("")
    md_lines.append(
        "Snapshot of how OpenVal's cashflow report compares to each of the 5 "
        "Argus Enterprise Cash Flow exports. Generated by "
        "`scripts/argus_sweep.py`."
    )
    md_lines.append("")
    md_lines.append("## Deal shapes")
    md_lines.append("")

    shape_rows = []
    drift_blocks: list[tuple[str, pd.DataFrame | None]] = []

    for f in fixtures:
        cf = read_argus_cashflow_xls(f)
        name = cf.property_name
        ann = _annualize_monthly(cf.monthly, cf.monthly.shape[1] // 12)
        signature = _shape_signature(ann)
        shape_rows.append({"deal": name, **signature})

        print(f"\n=== {name} ===")
        for k, v in signature.items():
            print(f"  {k}: {v}")

        stub_module = STUBS.get(name)
        openval_ann = _build_openval_for(Path(f), stub_module)
        if openval_ann is None:
            print("  [no stub — drift not computed]")
            drift_blocks.append((name, None))
            continue
        argus_ann = ann.reindex(ARGUS_CASHFLOW_ROWS).iloc[:, :openval_ann.shape[1]]
        drift = _drift_summary(argus_ann, openval_ann)
        drift_blocks.append((name, drift))
        within_25 = (drift["max_abs_drift"] < 25).sum()
        total = len(drift)
        print(f"  Drift: {within_25}/{total} rows within $25 (Y1..Y10)")

    # Shapes table
    md_lines.append("| Deal | Y1 lease-up? | Mid-hold A&T years | Vacancy line | Mid-hold TI/LC years |")
    md_lines.append("| --- | --- | --- | --- | --- |")
    for r in shape_rows:
        lease_up = "yes" if (r["Y1 A&T vacancy?"] or r["Y1 free rent?"]) else "no"
        md_lines.append(
            f"| {r['deal']} | {lease_up} | "
            f"{r['Mid-hold A&T years'] or '—'} | "
            f"{r['Vacancy allowance']} | "
            f"{r['Mid-hold TI/LC years'] or '—'} |"
        )
    md_lines.append("")

    # Drift section per deal that has a stub
    md_lines.append("## Drift vs Argus (deals with stubs)")
    md_lines.append("")
    for name, drift in drift_blocks:
        md_lines.append(f"### {name}")
        md_lines.append("")
        if drift is None:
            md_lines.append("_No stub registered — drift not computed. Add a stub to `scripts/argus_sweep.py::STUBS` once one exists._")
            md_lines.append("")
            continue
        within_25 = (drift["max_abs_drift"] < 25).sum()
        md_lines.append(f"**{within_25} / {len(drift)} rows within $25** across Y1..Y10.")
        md_lines.append("")
        md_lines.append("| Row | Max abs drift | Verdict |")
        md_lines.append("| --- | --- | --- |")
        for _, row in drift.iterrows():
            md_lines.append(f"| {row['row']} | ${row['max_abs_drift']:,.0f} | {row['verdict']} |")
        md_lines.append("")

    # Patterns observed
    md_lines.append("## Patterns observed across deals")
    md_lines.append("")
    md_lines.append(
        "**Lease-up at acquisition** (CocoMar, Rialto, Southeast Austin, "
        "Unbound) — A&T vacancy + free rent in Y1. Modeled today via "
        "`MarketLeasingAssumption.downtime_months_new` + "
        "`Lease.free_rent_months`. Works for single-tenant deals (Unbound)."
    )
    md_lines.append("")
    md_lines.append(
        "**Mid-hold rollover events** (Telephone Road, partial Rialto / "
        "Southeast Austin) — A&T vacancy and TI/LC bills appear in mid-hold "
        "years when a tenant rolls. Not yet modeled — needs multi-tenant "
        "lease support (one Lease per tenant) and the projector to emit "
        "TI/LC for MLA-spawned segments. Phase B+ schema work."
    )
    md_lines.append("")
    md_lines.append(
        "**Year-varying Vacancy Allowance / Credit Loss** (Telephone Road "
        "shows constant % of SBR in stable years but spikes during rollover "
        "years). Today `Property.general_vacancy_pct` is a single fraction. "
        "Phase B option: extend to per-year `dict[int, Decimal]` or auto-"
        "compute during transitional years."
    )
    md_lines.append("")
    md_lines.append(
        "**Property Management Fee** is percentage-of-revenue (varies "
        "year-to-year). Already supported via "
        "`opex_with_pct_of_revenue_fee` helper + `Property.opex_categories`."
    )
    md_lines.append("")

    # Schema follow-ups
    md_lines.append("## Schema follow-ups to close remaining gaps")
    md_lines.append("")
    md_lines.append("1. **Multi-tenant rent rolls + speculative rollover TI/LC.** Today the projector emits TI/LC only at original lease commencement. MLA-spawned new-tenant segments should bill TI/LC on their commencement too. Unblocks the leasing-cost rows in Telephone Road, Rialto, Southeast Austin.")
    md_lines.append("2. **Per-year vacancy / credit loss overrides.** Either `Property.general_vacancy_by_year: dict[int, Decimal]` or computed from rollover detection. Unblocks Vacancy Allowance / Credit Loss matching in Telephone Road.")
    md_lines.append("3. **`Property.capex_categories` for Capital Reserves** is shipped — but Telephone Road's reserves of $58K growing 3%/yr aren't in any stub yet. Mechanical to add once a stub is built.")
    md_lines.append("4. **Y11 partial-year handling.** Every deal's Y11 is mid-year-anchored (period starts month ≠ Jan for some deals). Projection truncation in the engine already handles this; reporter output just needs a label that flags partial years.")
    md_lines.append("")

    out_md = ROOT / "docs" / "ARGUS_SWEEP.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines))
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    main()
