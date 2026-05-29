# OpenVal

Open-source commercial real estate underwriting — lease-level cash flow modeling, expense recoveries, debt, reversion, and IRR. An open alternative to [Argus Enterprise](https://www.altusgroup.com/argus/).

## Why

[Argus Enterprise](https://www.altusgroup.com/argus/) is the industry-standard tool for CRE underwriting. It is closed-source, expensive, and gated. As of May 2026, no open-source equivalent exists.

This project fills that gap. The goal is an open, scriptable, lease-level CRE underwriting engine — Argus-grade depth where it matters, no subscription.

## Status

**Pre-alpha.** End-to-end deterministic DCF works: lease → cashflow → recoveries → NOI → debt service → reversion → unlevered + levered IRR + equity multiple. 43 tests passing.

## Phase 1 scope

- [x] Lease data model (NNN / MG / FSG, base rent steps, free rent, TI/LC, percentage rent, renewal options)
- [x] Lease cashflow projector (monthly base rent, step-ups, free rent abatement, TI, LC)
- [x] Rent roll aggregation (sum many leases onto a common timeline)
- [x] Expense recovery engine (NNN, MG base year, MG expense stop, FSG, annual recovery cap)
- [x] Debt: amortization, IO period, balloon
- [x] DCF: NOI assembly → reversion → unlevered & levered IRR + equity multiple
- [ ] Rent roll I/O (CSV/Excel import)
- [ ] Demo notebook end-to-end

## Phase 2+

Forward (year N+1) NOI for reversion (currently trailing-12), market leasing assumptions on rollover, partition reports, multi-property portfolio rollup, gross-up for partial occupancy, percentage rent against actual sales, Argus `.aeex` file import, optional rangekeeper integration for stochastic / Monte Carlo / real-options modeling.

## Install

```bash
pip install -e ".[dev]"
pytest
```

The optional `engine` extra (`pip install -e ".[dev,engine]"`) pulls in [rangekeeper](https://github.com/daniel-fink/rangekeeper) for stochastic / Monte Carlo modeling. It pins Python `>=3.10,<3.13`, so install it in a 3.12 venv if needed. The core deterministic DCF in this package works on 3.11+ and has no rangekeeper dependency.

## License

MIT.
