"""Generate a realistic industrial-deal sample workbook for OpenVal.

The workbook layout mirrors Argus Enterprise's tab organization: each
assumption category lives on its own sheet so you can toggle inputs in
isolation, then re-run ``scripts/run_workbook.py`` to see updated outputs.

Output: ``docs/sample_workbook.xlsx``

Input sheets
============

notes                Read-me and tab map
property             Building identity (name, type, address, rentable SF)
timing               acquisition_date, hold_years, reversion_basis
inflation            Annual growth rates (rent, opex, market rent, capex)
purchase             acquisition_price, sale_costs_pct, exit_cap_rate
debt                 Loan terms (principal, rate, amort, term, IO)
vacancy_credit       general_vacancy_pct, credit_loss_pct
opex                 year, annual_opex
capex                year, annual_capex (optional)
leases               One row per lease (matches read_rent_roll_excel)
rent_steps           In-lease escalations, joined on suite_id
mla                  Market Leasing Assumptions, one row per suite_id

Output sheets (overwritten by run_workbook.py)
==============================================

cashflows            Monthly DCF detail
annual_summary       Year-by-year rollup
reversion            Terminal NOI + sale math
irr_summary          Unlevered + levered IRR under all 3 conventions
sensitivity          5x5 grid: exit_cap_rate × acquisition_price
yield_matrix         Year-by-year going-in / current yield
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "docs" / "sample_workbook.xlsx"


# ----------------------------------------------------------------------
# Sheet builders
# ----------------------------------------------------------------------


def _notes_sheet() -> pd.DataFrame:
    rows = [
        ("HOW TO USE", ""),
        ("1.", "Edit any input sheet (property / leases / debt / etc.)."),
        ("2.", "Save the workbook."),
        ("3.", "Run: python scripts/run_workbook.py docs/sample_workbook.xlsx"),
        ("4.", "Re-open — output sheets (cashflows, annual_summary, irr_summary, etc.) are refreshed in place."),
        ("", ""),
        ("INPUT SHEETS", ""),
        ("property", "Building identity (name, type, rentable SF)"),
        ("timing", "Acquisition date, hold length, reversion basis (trailing-12 or forward NOI)"),
        ("inflation", "Annual growth rates by category — drives MLA market_rent_growth, opex schedule extrapolation"),
        ("purchase", "Acquisition price, sale costs %, exit cap rate"),
        ("debt", "Loan principal, rate, amortization, term, interest-only period"),
        ("vacancy_credit", "General vacancy %, credit loss %, opex non-recoverable %, opex gross-up at occupancy %"),
        ("refinance", "Optional mid-hold refinance — effective date, new loan terms, prepayment penalty %. Leave fields blank to skip."),
        ("waterfall", "JV equity waterfall: LP/GP equity shares, preferred return, up to 3 promote tiers (LP IRR hurdle + GP promote %)"),
        ("cpi", "Annual CPI rates used for CPI-indexed lease escalators (referenced from rent_steps if any escalator's rent is left blank)"),
        ("opex", "Year-by-year operating expense schedule (must cover hold; one extra year if reversion_basis=forward)"),
        ("capex", "Year-by-year capital expense schedule (optional)"),
        ("leases", "Rent roll — one row per lease"),
        ("rent_steps", "In-lease escalations, joined on suite_id (optional; if blank a single step from leases.base_rent_psf is used)"),
        ("mla", "Market Leasing Assumptions, one row per suite_id. Required for any lease that expires inside the projection window"),
        ("", ""),
        ("OUTPUT SHEETS (overwritten on each run)", ""),
        ("cashflows", "Monthly DCF detail. Columns: gross_rent, free_rent_abatement, general_vacancy, credit_loss, recoveries, egi, opex, noi, capex, ti, lc, debt_service, ncf_unlevered, ncf_levered, loan_balance"),
        ("annual_summary", "Year-by-year rollup of the above"),
        ("reversion", "Terminal NOI, gross/net sale, loan payoff, net-to-equity, basis used"),
        ("irr_summary", "Unlevered + levered IRR under monthly_annualized, annual_end_of_year, annual_mid_year conventions. Plus equity multiples."),
        ("sensitivity", "5x5 grid: exit cap rate (rows) × acquisition price (cols), unlevered IRR cells (mid-year convention)"),
        ("yield_matrix", "Year-by-year going-in / current yield: NOI / acquisition price"),
        ("", ""),
        ("ARGUS PARITY", ""),
        ("Reversion", "Set timing!reversion_basis = 'forward' to match Argus's year-N+1 / exit-cap convention. 'trailing' = trailing-12 / exit-cap."),
        ("IRR", "Argus reports mid-year IRR by default. See irr_summary.annual_mid_year."),
        ("MLA blending", "OpenVal blends renewal / new-tenant outcomes by probability, matching Argus's Schedule of Prospective Cashflow. Per-lease MLA today; named profiles planned."),
        ("Vacancy", "General vacancy + credit loss are independent deductions on EGI, compounding with MLA downtime. Set general_vacancy_pct=0 to rely solely on MLA-driven absorption vacancy."),
    ]
    return pd.DataFrame(rows, columns=["item", "description"])


def _property_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("name", "Sample Industrial Distribution Center"),
            ("property_type", "Industrial"),
            ("address_line_1", "12345 Logistics Pkwy"),
            ("city", "Sugar Land"),
            ("state", "TX"),
            ("country", "USA"),
            ("rentable_sf", 100_000),
        ],
        columns=["field", "value"],
    )


def _timing_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("acquisition_date", "2026-01-01"),
            ("hold_years", 5),
            ("reversion_basis", "forward"),  # forward = Argus convention, trailing = OpenVal default
        ],
        columns=["field", "value"],
    )


def _inflation_sheet() -> pd.DataFrame:
    """Argus-style category-level growth rates.

    Currently consumed:
        opex_growth_pct           → drives the opex schedule beyond explicit years
        capex_growth_pct          → drives the capex schedule (unused if capex sheet covers all years)
        market_rent_growth_pct    → cross-checked against MLA market_rent_growth_pct

    Reserved (informational only for v1):
        rent_growth_pct           → in-lease escalations live on rent_steps
        cpi_pct                   → Phase 2 CPI-indexed leases
    """
    return pd.DataFrame(
        [
            ("rent_growth_pct", 0.03),
            ("opex_growth_pct", 0.03),
            ("capex_growth_pct", 0.03),
            ("market_rent_growth_pct", 0.03),
            ("cpi_pct", 0.025),
        ],
        columns=["category", "annual_rate"],
    )


def _purchase_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("acquisition_price", 40_000_000),
            ("acquisition_costs_pct", 0.02),  # closing costs % of purchase price
            ("sale_costs_pct", 0.02),
            ("exit_cap_rate", 0.07),
        ],
        columns=["field", "value"],
    )


def _debt_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("loan_principal", 24_000_000),  # 60% LTV
            ("loan_rate_annual", 0.055),
            ("loan_amortization_years", 30),
            ("loan_term_years", 10),
            ("loan_interest_only_years", 0),
        ],
        columns=["field", "value"],
    )


def _refinance_sheet() -> pd.DataFrame:
    """Optional mid-hold refinance. Leave all rows empty to skip."""
    return pd.DataFrame(
        [
            ("refi_effective_date", "2029-01-01"),  # year 3
            ("refi_new_principal", 28_000_000),  # cash-out (was 24M)
            ("refi_new_rate_annual", 0.045),  # rate compression
            ("refi_new_amortization_years", 30),
            ("refi_new_term_years", 10),
            ("refi_new_interest_only_years", 0),
            ("refi_prepayment_penalty_pct", 0.01),
        ],
        columns=["field", "value"],
    )


def _vacancy_credit_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("general_vacancy_pct", 0.05),
            ("credit_loss_pct", 0.005),
            ("opex_non_recoverable_pct", 0.08),  # 8% mgmt/marketing not pass-through
            ("opex_gross_up_at_occupancy_pct", 0.95),  # gross up to 95% occupancy
        ],
        columns=["field", "value"],
    )


def _waterfall_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("lp_equity_share", 0.90),
            ("gp_equity_share", 0.10),
            ("preferred_return_pct", 0.08),
            # Promote tier 1: 20% to GP above 8% LP IRR
            ("tier1_lp_irr_hurdle", 0.08),
            ("tier1_gp_promote_pct", 0.20),
            # Promote tier 2: 30% to GP above 12% LP IRR
            ("tier2_lp_irr_hurdle", 0.12),
            ("tier2_gp_promote_pct", 0.30),
            # Promote tier 3: 40% to GP above 18% LP IRR (super-promote)
            ("tier3_lp_irr_hurdle", 0.18),
            ("tier3_gp_promote_pct", 0.40),
        ],
        columns=["field", "value"],
    )


def _cpi_sheet() -> pd.DataFrame:
    """Annual CPI rates for CPI-indexed lease escalators (used if any lease references CPI)."""
    return pd.DataFrame(
        [
            {"year": y, "cpi_rate": round(0.025 + 0.005 * (y - 2026), 4)}
            for y in range(2026, 2032)
        ]
    )


def _opex_sheet() -> pd.DataFrame:
    base = 1_500_000
    rows = []
    for i, year in enumerate(range(2026, 2032)):  # 6 yrs (hold + 1 for forward NOI)
        rows.append({"year": year, "annual_opex": round(base * (1.03 ** i), 2)})
    return pd.DataFrame(rows)


def _capex_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"year": 2027, "annual_capex": 150_000},  # roof TPO patch
            {"year": 2029, "annual_capex": 200_000},  # parking lot resurface
        ]
    )


def _leases_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "suite_id": "A",
                "tenant_name": "Acme Distribution",
                "area_sf": 60_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",  # rolls right at hold end — MLA fills year 6
                "base_rent_psf": 32.00,
                "expense_structure": "NNN",
                "free_rent_months": 0,
                "ti_psf": 0,
                "lc_pct_first_year_rent": 0,
            },
            {
                "suite_id": "B",
                "tenant_name": "Beta Logistics",
                "area_sf": 40_000,
                "start_date": "2026-01-01",
                "end_date": "2029-01-01",  # rolls mid-hold — MLA generates blended segments
                "base_rent_psf": 30.00,
                "expense_structure": "NNN",
                "free_rent_months": 3,
                "ti_psf": 25,
                "lc_pct_first_year_rent": 0.05,
            },
        ]
    )


def _rent_steps_sheet() -> pd.DataFrame:
    rows = []
    # Suite A: 3% annual escalation
    for i in range(5):
        rows.append(
            {
                "suite_id": "A",
                "start_date": f"{2026 + i}-01-01",
                "annual_psf": round(32.00 * (1.03 ** i), 4),
            }
        )
    # Suite B: 3% annual escalation
    for i in range(3):
        rows.append(
            {
                "suite_id": "B",
                "start_date": f"{2026 + i}-01-01",
                "annual_psf": round(30.00 * (1.03 ** i), 4),
            }
        )
    return pd.DataFrame(rows)


def _mla_sheet() -> pd.DataFrame:
    """Argus requires every lease to have an MLP pointer. We follow that
    pattern: both suites get an MLA so the projector knows what to roll into.
    """
    return pd.DataFrame(
        [
            {
                "suite_id": "A",
                "market_rent_psf": 33.00,  # current market for big-box industrial
                "market_rent_growth_pct": 0.03,
                "new_term_months": 60,
                "rent_escalation_pct": 0.03,
                "free_rent_months_new": 3,
                "free_rent_months_renewal": 0,
                "ti_psf_new": 15,
                "ti_psf_renewal": 5,
                "lc_pct_new": 0.05,
                "lc_pct_renewal": 0.02,
                "renewal_probability": 0.60,  # incumbent renewal heavy
                "downtime_months_new": 6,
                "renewal_market_discount_pct": 0.05,  # 5% off market for renewal
                "expense_structure": "NNN",
            },
            {
                "suite_id": "B",
                "market_rent_psf": 32.00,
                "market_rent_growth_pct": 0.03,
                "new_term_months": 60,
                "rent_escalation_pct": 0.03,
                "free_rent_months_new": 4,
                "free_rent_months_renewal": 1,
                "ti_psf_new": 20,
                "ti_psf_renewal": 5,
                "lc_pct_new": 0.05,
                "lc_pct_renewal": 0.02,
                "renewal_probability": 0.50,
                "downtime_months_new": 6,
                "renewal_market_discount_pct": 0.05,
                "expense_structure": "NNN",
            },
        ]
    )


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------


SHEET_BUILDERS: list[tuple[str, callable]] = [
    ("notes", _notes_sheet),
    ("property", _property_sheet),
    ("timing", _timing_sheet),
    ("inflation", _inflation_sheet),
    ("purchase", _purchase_sheet),
    ("debt", _debt_sheet),
    ("refinance", _refinance_sheet),
    ("vacancy_credit", _vacancy_credit_sheet),
    ("waterfall", _waterfall_sheet),
    ("cpi", _cpi_sheet),
    ("opex", _opex_sheet),
    ("capex", _capex_sheet),
    ("leases", _leases_sheet),
    ("rent_steps", _rent_steps_sheet),
    ("mla", _mla_sheet),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        for name, build in SHEET_BUILDERS:
            build().to_excel(writer, sheet_name=name, index=False)
    print(f"Wrote {OUT}")
    print(f"Sheets: {', '.join(name for name, _ in SHEET_BUILDERS)}")


if __name__ == "__main__":
    main()
