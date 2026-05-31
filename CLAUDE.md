# CLAUDE.md — OpenVal

Open-source commercial real estate underwriting engine — a lease-level alternative to Argus Enterprise. Phase 1 ships deterministic DCF; rangekeeper kept as an optional dependency for stochastic Phase 2.

## Stack
Python 3.11+ (3.13 recommended for full Phase-2 rangekeeper compat). pydantic v2 for schemas + validation. pandas for cashflow projection. numpy-financial for IRR. pytest. Hatchling build backend. MIT license. Reposistory at github.com/aanfinson00/openval.

## Iteration principles

### 1. Append-only schema changes
Never rename `Lease.area_sf` or remove `RentStep`. Always add. Old fixtures, validation deals, and DeLisle case data must keep parsing forever — that's how we know the engine's outputs are stable.

### 2. Use `Field(default=None)` + `Optional` for new fields
Adds without breaking old test fixtures. Examples:
```python
new_optional_field: Optional[Decimal] = Field(default=None)
```
Old `Lease(...)` calls without the new arg keep working.

### 3. Pydantic `model_config = ConfigDict(extra='allow')` on data-collecting models
When importing data from outside the engine (`.aeex`, CSV, A.CRE Ai1), accept unknown fields rather than rejecting. Better to round-trip extra data than to lose it.

### 4. Save raw input alongside parsed
When parsing an `.aeex` or OM PDF, save the raw text/bytes alongside the structured `Property` object. If extraction logic improves later, you can re-parse without losing source. Convention: `validation/fixtures/` for raw, `validation/parsed/` for structured.

### 5. Validation deals are gospel
Every validation deal in `validation/` reproduces a published source (DeLisle Case 5, eventually A.CRE Ai1, etc.). Their expected outputs are pinned. **If a code change moves a validation deal's IRR by more than 0.01 pp, you've introduced a bug or the source moved.** Investigate, don't paper over.

## Schema-change checklist
When adding a real field to Property / Lease / Loan / RentRollRow etc.:
1. **Pydantic schema** in `src/openval/lease.py` / `property.py` / `debt.py` — `Optional` + `Field(default=None)` first.
2. **Update projector** if the field affects cashflows — `src/openval/cashflow.py` reads new field, projects accordingly.
3. **Update validation deal** in `validation/` if it changes any expected numbers — re-run and re-pin.
4. **Add a test** in `tests/` exercising the new field's behavior.
5. **Update README Phase 1 / Phase 2 list** if the field unlocks a feature.

## Don't touch
- rangekeeper integration — Phase 2 only. Use plain pydantic + pandas for Phase 1.
- `validation/fixtures/` — golden data, don't regenerate.
- Decimal vs float — leases use `Decimal`, projection runs in `float`. Don't mix.

## Common tasks
- **Install** (Python 3.13 venv recommended): `python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- **Run tests**: `.venv/bin/pytest`
- **Run validation**: `.venv/bin/python validation/delisle_case5.py`
- **Re-pin a validation deal**: edit the `PUBLISHED` dict in the validation script, justify in the commit message.

## Architecture notes
- **Lease as data model** (`Lease`, `RentStep`, `PercentageRent`, `RenewalOption`) — immutable, pydantic-validated.
- **Cashflow projector** (`project_lease`, `project_rent_roll`) — pure pandas DataFrames per month.
- **Recovery engine** (`project_recoveries`) — NNN / MG base year / MG expense stop / FSG.
- **Debt** (`Loan`, `amortize_loan`) — IO + balloon + monthly amortization.
- **DCF** (`project_property`) — wires it all together → NOI → debt service → reversion → IRR + EM.
- **Reversion** is selectable via `Property.reversion_basis`: `"trailing"` (default, trailing-12 NOI / cap) or `"forward"` (Argus convention, year N+1 NOI / cap — projects one extra year past the hold, requires opex_annual to cover it).
- **IRR convention** is selectable per call via `result.irr(convention=, levered=)`. Options: `"monthly_annualized"` (default, matches `result.unlevered_irr`), `"annual_end_of_year"` (Excel default), `"annual_mid_year"` (Argus). The first two use `numpy_financial.irr`; mid-year uses an in-house bisection (no scipy needed).
- **Market Leasing Assumptions** (`MarketLeasingAssumption`) attach to a `Lease` via `market_leasing_assumption`. When the lease expires inside the projection window, `expand_with_mla` in `cashflow.py` recursively branches into a renewal segment (weight = `renewal_probability`) and a new-tenant segment (weight = `1 − p`); each speculative child inherits the same MLA so rollover chains automatically. Cashflows + recoveries are summed across all weighted segments. Per-lease MLA today; v2 plans property-level named profiles (Argus MLP equivalent). Reimbursable recoveries during downtime are excluded (segment dropped); Argus has a toggle for this — TODO for v2.
- **Vacancy + credit loss**: `Property.general_vacancy_pct` and `Property.credit_loss_pct` are fractions of gross potential rent applied as separate deductions to EGI (NOT to opex). Default 0 (no deduction). Compound additively with MLA downtime — they are conceptually independent (background vacancy vs absorption/turnover vacancy). For Argus-aligned single-source vacancy, set general_vacancy_pct=0 and rely on MLA downtime.
- **I/O**: `openval.io.read_rent_roll_excel(path)` / `read_rent_roll_csv(path)` import a generic lease workbook (documented column schema; optional `rent_steps` sheet for escalations). `openval.io.read_avux_metadata(path)` parses Argus `.avux` package metadata (Summary.xml + Info.xml); the full Input.xml payload is encrypted at the Argus product level and is not readable without Argus's COM API — users should export `.aeex` from Argus for full deal import (the AEEX parser is the next Phase-2 work item).
