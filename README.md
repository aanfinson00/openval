# proforma-engine

Open-source commercial real estate underwriting — lease-level cash flow modeling on top of [rangekeeper](https://github.com/daniel-fink/rangekeeper).

## Why

[Argus Enterprise](https://www.altusgroup.com/argus/) is the industry-standard tool for CRE underwriting. It is closed-source, expensive, and gated. As of May 2026, no open-source equivalent exists. The only credible OSS foundation is [rangekeeper](https://github.com/daniel-fink/rangekeeper) (MPL-2.0), which implements the canonical Geltner/de Neufville DCF methodology — but operates at the top-down property level (NOI in, IRR out) and does not model rent rolls, expense recoveries, or market leasing assumptions.

This project fills that gap. The goal is an open, scriptable, lease-level CRE underwriting engine — Argus-grade depth where it matters, no subscription.

## Status

**Pre-alpha.** Lease data model lands first. Cashflow projector, recovery engine, and rangekeeper integration in progress.

## Phase 1 scope

- [x] Lease data model (NNN / MG / FSG, base rent steps, free rent, TI/LC, percentage rent, renewal options)
- [ ] Rent roll (collection of leases, CSV/Excel import)
- [ ] Lease cashflow projector (monthly base rent + free rent abatement)
- [ ] Expense recovery engine (CAM/tax/insurance pass-through, base years, stops, gross-ups, caps)
- [ ] rangekeeper integration (feed lease cashflows into NOI → NCF → reversion → IRR)
- [ ] Demo notebook: small office building, mixed lease structures, debt, reversion

## Phase 2+

Market leasing assumptions on rollover, partition reports, multi-property portfolio rollup, Argus `.aeex` file import.

## Install

```bash
pip install -e ".[dev]"
pytest
```

The `engine` extra (`pip install -e ".[dev,engine]"`) pulls in rangekeeper, which currently pins Python `>=3.10,<3.13`. Until that loosens, run the rangekeeper-integrated path in a Python 3.12 venv. The lease layer itself works on 3.11+.

## License

MIT. rangekeeper is MPL-2.0 and is depended on as an unmodified library.
