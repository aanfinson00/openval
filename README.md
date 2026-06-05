# OpenVal

Open-source commercial real estate underwriting — lease-level cash flow modeling, expense recoveries, debt, reversion, and IRR. An open alternative to [Argus Enterprise](https://www.altusgroup.com/argus/).

## Why

[Argus Enterprise](https://www.altusgroup.com/argus/) is the industry-standard tool for CRE underwriting. It is closed-source, expensive, and gated. As of May 2026, no open-source equivalent exists.

This project fills that gap. The goal is an open, scriptable, lease-level CRE underwriting engine — Argus-grade depth where it matters, no subscription.

## Status

**Pre-alpha.** End-to-end deterministic DCF with rollover modeling, multi-convention IRR, mid-hold refinance, JV waterfall, and Excel rent roll I/O. **133 tests passing.**

## Phase 1 (shipped)

- Lease data model (NNN / MG / FSG, base rent steps, free rent, TI/LC, percentage rent, renewal options, CPI escalators)
- Lease cashflow projector with rent roll aggregation
- Expense recovery engine (NNN, MG base year, MG expense stop, FSG, annual recovery cap)
- Debt amortization with IO period, balloon, and mid-hold refinance
- DCF: NOI → reversion → unlevered & levered IRR + equity multiple
- Reversion basis selectable: trailing-12 NOI or Argus-convention forward (year N+1) NOI
- IRR convention selectable per call: monthly annualized, annual end-of-year, annual mid-year (Argus)

## Phase 2 (shipped)

- **Market Leasing Assumptions** on rollover (per-lease MLA → renewal/new probability-weighted segments, chained through hold)
- **General vacancy + credit loss** as EGI deductions
- **CSV/Excel rent roll import** via `openval.io.read_rent_roll_excel`
- **Sensitivity matrix** over 7 axes × 6 metrics
- **Argus `.avux` metadata reader** (Input.xml payload is encrypted at the Argus product level — full data import is gated on `.aeex` export)
- **Sample interactive workbook** mirroring Argus-style tab organization

## Phase 3 (shipped)

- **Acquisition closing costs** included in initial equity basis
- **DSCR + debt yield** on monthly cashflow for covenant tracking
- **Stabilized NOI + going-in cap** on the underwriting result
- **Mark-to-market** per-lease report (in-place rent vs MLA market rent)
- **Percentage rent** projector for retail / restaurant deals
- **CPI-indexed lease escalators** with floor/ceiling collars
- **Mid-hold refinance** with prepayment penalty modeling
- **Vacant suite handling** for lease-up underwriting
- **Reimbursement gross-up** at sub-threshold occupancy
- **JV equity waterfall** with LP/GP equity, preferred return, and promote tiers
- **Opex non-recoverable %** (lite multi-line opex)

## Phase 4 backlog

`.aeex` full-deal import, portfolio rollup across multiple Property instances, named scenario manager, stochastic / Monte Carlo via rangekeeper integration, full opex category decomposition (CAM / taxes / insurance separately).

## Install

```bash
pip install -e ".[dev]"
pytest
```

The optional `engine` extra (`pip install -e ".[dev,engine]"`) pulls in [rangekeeper](https://github.com/daniel-fink/rangekeeper) for stochastic / Monte Carlo modeling. It pins Python `>=3.10,<3.13`, so install it in a 3.12 venv if needed. The core deterministic DCF in this package works on 3.11+ and has no rangekeeper dependency.

## Interactive sample workbook

A self-contained 15-tab industrial-deal sample lives at `docs/sample_workbook.xlsx`. Edit any input tab, save, then:

```bash
python scripts/run_workbook.py docs/sample_workbook.xlsx
```

Output sheets (cashflows, annual_summary, irr_summary, reversion, yield_matrix, sensitivity, waterfall_schedule, waterfall_summary, mark_to_market, rent_roll_in) are overwritten in place. Pressure-test the engine against your own deal economics without writing Python.

## Quickstart

```python
from datetime import date
from decimal import Decimal
from openval import (
    ExpenseStructure, Lease, Loan, Property, RentStep,
    project_property, run_waterfall, Waterfall, PromoteTier,
)

lease = Lease(
    suite_id="A", tenant_name="Acme", area_sf=50_000,
    start_date=date(2026, 1, 1), end_date=date(2031, 1, 1),
    base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
    expense_structure=ExpenseStructure.NNN,
)
prop = Property(
    name="Building", rentable_sf=50_000, leases=[lease],
    opex_annual={y: Decimal("500000") for y in range(2026, 2032)},
    acquisition_date=date(2026, 1, 1),
    acquisition_price=Decimal("15000000"),
    hold_years=5, exit_cap_rate=Decimal("0.07"),
    reversion_basis="forward",
    loan=Loan(
        principal=Decimal("9000000"), rate_annual=Decimal("0.055"),
        amortization_years=30, term_years=10,
    ),
)
result = project_property(prop)
print(f"Unlevered IRR (mid-year): {result.irr(convention='annual_mid_year'):.2%}")
print(f"Levered IRR (mid-year):   {result.irr(convention='annual_mid_year', levered=True):.2%}")
print(f"Going-in cap:             {result.going_in_cap:.2%}")
print(f"Stabilized cap:           {result.stabilized_cap:.2%}")

# Optional JV waterfall
wf = run_waterfall(result, Waterfall(
    lp_equity_share=Decimal("0.9"), gp_equity_share=Decimal("0.1"),
    preferred_return_pct=Decimal("0.08"),
    promote_tiers=[PromoteTier(lp_irr_hurdle=Decimal("0.08"), gp_promote_pct=Decimal("0.2"))],
))
print(f"LP EM: {wf.lp_equity_multiple:.2f}x, GP EM: {wf.gp_equity_multiple:.2f}x")
```

## License

MIT.
