# Argus Enterprise Feature Checklist

A cross-source synthesis of Argus Enterprise capabilities, used as the roadmap target for OpenVal.

## Methodology

Compiled from four parallel research passes (May 2026):

1. **Altus XML Integration Schema** (Scribd AE 11.0.5, Yumpu 9.1) — schema-driven feature catalog. Anything modelable in Argus appears as an XML element.
2. **Competitor comparison tables & integration docs** (Rockport VAL, Forbury, Apers, Lightbox CashFlow, Assess+RE, PropertyMetrics, SoftwareFinder, Altus marketing). Features that Argus competitors call out by name.
3. **Training curricula + job postings + practitioner community** (Altus 2-Day, Cert Prep, eLearning, NAIOP ASC, ICSC, UCLA Extension, 40+ job postings, WSO/ACG/Realogic). Real-world frequency.
4. **YouTube tutorial titles** scraped via `yt-dlp --flat-playlist` from 14 channels (253 raw titles, 162 unique). Surfaces what practitioners actually search for.

Triangulation: features mentioned by 3+ sources are **CORE** (table-stakes for any serious Argus alternative); 2 sources = **STD**; 1 source = **LONG-TAIL**.

## OpenVal coverage today

- ✅ **Done** (Phase 1+, v0.1.0): lease model, cashflow projector, NNN/MG/FSG recoveries, debt amortization (IO + balloon), reversion (trailing-12 *and* forward-NOI / cap, selectable via `Property.reversion_basis`), unlevered + levered IRR (monthly / annual EOY / annual mid-year), equity multiple, rent step-ups, free rent, TI/LC, **Market Leasing Assumptions on rollover** (per-lease MLA → probability-weighted renewal/new branching with downtime / market growth / renewal discount, chaining through hold)
- 🟡 **Partial**: percentage rent (data model only, no projector yet); recovery cap (annual only); MLA reimbursements during downtime (excluded today, Argus has a toggle)
- ❌ **Gaps**: ~50 CORE features and ~80 STD/LONG-TAIL features. Top priorities laid out below.

## Roadmap impact

**Phase 2 priorities** (closes the gap to "serious Argus alternative"):
1. ~~**Market Leasing Assumptions on rollover**~~ — ✅ v1 shipped. Per-lease `MarketLeasingAssumption` triggers probability-weighted renewal/new branching with downtime, market-rent growth, renewal discount, new-vs-renewal free rent / TI / LC. Chains recursively through the hold. v2: promote to named property-level profiles (true Argus MLP), reimbursable recoveries during downtime toggle.
2. ~~**Forward NOI for reversion**~~ — ✅ shipped; opt in via `Property(reversion_basis="forward")`. DeLisle Case 5 forward-NOI mode now matches published reversion within $10 and levered IRR within 0.5 pp of derived pre-tax target.
3. **Vacancy & credit loss** — general vacancy, absorption & turnover vacancy, gross-up checkbox.
4. **CSV/Excel rent roll import** — adoption blocker; nobody types in 200 leases by hand.
5. **`.aeex` / `.aeix` import** — Argus's XML export format is public; parsing is tolerated (Forbury/Lightbox/Assess+RE all do it).
6. **Sensitivity matrix** — IRR matrix on yield / growth / cap rate. Built-in feature competitors all replicate.

**Bonus shipped:**
- `UnderwritingResult.irr(convention=, levered=)` — monthly_annualized | annual_end_of_year | annual_mid_year. Lets users match their Excel or Argus yield outputs.

**Phase 3+** (parity push):
- Equity waterfalls (GP/LP, preferred return, promote tiers) — Argus itself offloads to ARGUS Taliance, most practitioners do this in Excel anyway
- Partition reports
- Portfolio rollup
- Audit log / model versioning
- Scenario manager
- Inflation overrides per category

---

## Full feature matrix

Legend: ✅ done · 🟡 partial · ❌ not yet · **CORE** = 3+ source mentions · STD = 2 · *long-tail* = 1

### 1. Property / Building

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Property name, type, area | ✅ | CORE | `Property` model |
| Multi-currency | ❌ | STD | Phase 3 |
| Property classifications (System / Property / Tenant) | ❌ | *long-tail* | Phase 3+ |
| Chart of Accounts (Header / Account / Detail levels) | ❌ | *long-tail* | Phase 3+ |
| Property attachments (docs, URLs) | ❌ | *long-tail* | Out of scope |
| Resource Base Collection (RBC) | ❌ | *long-tail* | Out of scope |

### 2. Rent Roll / Leases

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Lease-by-lease cashflow | ✅ | **CORE (top-cited)** | `Lease` + `project_lease()` |
| Tenant name, suite, area, start, end | ✅ | **CORE** | |
| Available Date (precedes start, for vacancy modeling) | ❌ | STD | Phase 2 (with vacancy) |
| Lease status (in-place / speculative / vacant) | ❌ | STD | Phase 2 |
| Upon Expiration: Renew / Market / Vacate / MTM | ❌ | **CORE** | Phase 2 (MLAs) |
| Renewal probability (per-lease weighting) | ❌ | **CORE** | Phase 2 |
| Lease options (renewal/extension) | 🟡 | STD | Data model has `RenewalOption`; no projector logic |
| Space Absorption (auto-generate leases from vacant space) | ❌ | *long-tail* | Phase 3+ |
| Lease abstracts generation | ❌ | STD | Out of scope (LLM territory) |
| Multi-tenant property modeling | ✅ | **CORE** | `Property.leases: list[Lease]` |

### 3. Lease Economics — Rent, Steps, Free Rent, TI/LC, % Rent

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Base rent ($/SF/Yr) | ✅ | **CORE** | |
| Rent steps (fixed schedule) | ✅ | **CORE** | `RentStep` |
| % annual increases | 🟡 | **CORE** | Modeled via explicit steps; helper for "auto 3%/yr" pending |
| CPI / index-linked rent | ❌ | **CORE** | Phase 2 |
| Free rent / abatements | ✅ | **CORE** | `free_rent_months` |
| TI allowance ($/SF) | ✅ | **CORE** | `ti_psf`, paid at commencement |
| TI new vs renewal differential | ❌ | **CORE** | Phase 2 (MLAs) |
| Leasing commissions (% of first-year rent) | ✅ | **CORE** | `lc_pct_first_year_rent` |
| LC new vs renewal differential | ❌ | **CORE** | Phase 2 (MLAs) |
| Percentage rent (natural + custom breakpoint) | 🟡 | STD | `PercentageRent` data model; no projector |
| Percentage rent against sales projection | ❌ | STD | Phase 3 |
| Miscellaneous rent (per-tenant other income) | ❌ | *long-tail* | Phase 2 |
| Estimated Rental Value (ERV) | ❌ | *long-tail* | Phase 3 |
| Rent Review dates | ❌ | *long-tail* | Phase 3 |
| Sales inflation & breakpoint growth | ❌ | *long-tail* | Phase 3 |

### 4. Expense Recoveries / Reimbursements

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| NNN (Net / triple net, pro-rata of all OpEx) | ✅ | **CORE** | |
| Modified Gross with base year stop | ✅ | **CORE** | `base_year` |
| Modified Gross with expense stop ($/SF) | ✅ | **CORE** | `expense_stop_psf` |
| Full Service Gross (no recovery) | ✅ | **CORE** | `FSG` enum |
| Base Year Stop -1 / +1 (BYS-1, BYS+1) | ❌ | STD | Phase 2 |
| Fixed Amount recovery | ❌ | STD | Phase 2 |
| Fixed Amount per Area recovery | ❌ | STD | Phase 2 |
| % Recoverable override at tenant level | ❌ | **CORE** | Phase 2 |
| Gross-Up % (separate from occupancy %) | ❌ | **CORE** | Phase 2 — heavily cited by practitioners |
| Recovery cap — annual % growth limit | ✅ | STD | `recovery_cap_pct` |
| Recovery cap — Max Ceiling Amount | ❌ | STD | Phase 2 |
| Expense Groups (pool expenses across recovery methods) | ❌ | **CORE** | Phase 2 |
| Reimbursable Expenses categorization | 🟡 | **CORE** | Single bucket today; need per-category |
| Non-recoverable expense flag | ❌ | *long-tail* | Phase 2 (with categories) |
| Apply-to-Tenants (link recovery to subpopulation) | ❌ | *long-tail* | Phase 3 |

### 5. Market Leasing Assumptions (MLA) — Argus's signature differentiator

**All ❌ — entire category is Phase 2 priority.**

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| MLA profile (named) | ❌ | **CORE** | Phase 2 |
| New Market vs Renewal Market rates | ❌ | **CORE** | |
| Renewal probability (weighted-average CF) | ❌ | **CORE** | |
| Market rent | ❌ | **CORE** | |
| Months vacant (downtime) | ❌ | **CORE** | |
| TI new vs renewal | ❌ | **CORE** | |
| LC new vs renewal | ❌ | **CORE** | |
| Free rent new vs renewal | ❌ | **CORE** | |
| Term length on rollover | ❌ | **CORE** | |
| Default recovery structure for new leases | ❌ | **CORE** | |
| Market rent inflation per year | ❌ | STD | |
| Per-MLA overrides for subsequent term generations | ❌ | *long-tail* | Phase 3 |
| "Continue Prior Lease" flag | ❌ | *long-tail* | Phase 3 |

### 6. Operating Expenses

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Annual OpEx total | ✅ | **CORE** | `opex_annual: dict[int, Decimal]` |
| Per-line item categories (CAM, Tax, Ins, Mgmt, etc.) | ❌ | **CORE** | Phase 2 |
| % Fixed / % Variable per expense | ❌ | STD | Phase 2 |
| Per-category inflation rate (with overrides) | ❌ | **CORE** | Phase 2 — top-cited practitioner trap |
| % of EGI line items (management fees) | ❌ | **CORE** | Phase 2 — circular ref, needs iterative solver |
| Reference-Only expenses (display, exclude from CF) | ❌ | *long-tail* | Phase 3 |
| Budget vs actuals comparison | ❌ | STD | Phase 3 (Argus Voyanta territory) |
| Subline expenses | ❌ | *long-tail* | Phase 3 |
| Frequency (annual / monthly OpEx) | 🟡 | STD | Annual only today; monthly distributed evenly |

### 7. CapEx

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Annual CapEx schedule | ✅ | STD | `capex_annual` field |
| Recoverable CapEx flag | ❌ | *long-tail* | Phase 3 |
| Capital Reserve / TI Reserve | ❌ | *long-tail* | Phase 2 |

### 8. Vacancy / Absorption / Credit Loss

**All ❌ — Phase 2 priority.**

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| General Vacancy rate (% of PGR / TRR / TTR / EGR methods) | ❌ | **CORE** | Phase 2 |
| Absorption & Turnover Vacancy | ❌ | **CORE** | Phase 2 |
| Credit & Collection Loss | ❌ | STD | Phase 2 |
| Vacancy gross-up checkbox | ❌ | STD | Phase 2 (with vacancy) |

### 9. Debt / Financing

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Single loan (amount, rate, amort, term) | ✅ | **CORE** | `Loan` |
| Interest-only period | ✅ | **CORE** | `interest_only_years` |
| Balloon at end of term | ✅ | **CORE** | Built into amortization |
| Separate amort years vs term years | ✅ | **CORE** | |
| Multiple debt tranches per property | ❌ | STD | Phase 2 |
| Refinance / Take-Out Loan | ❌ | **CORE** | Phase 2 |
| Variable interest rate (rate changes per period) | ❌ | STD | Phase 3 |
| Loan fees / origination | ❌ | STD | Phase 2 |
| DSCR calculation | ❌ | STD | Phase 2 |
| LTV / LTC calculation | 🟡 | STD | Computable from existing fields, no helper |
| Mezzanine / junior debt | ❌ | *long-tail* | Phase 3 |
| "Other Debt" tab (externally computed) | ❌ | *long-tail* | Phase 3 |

### 10. Reversion / Property Resale

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Capitalize NOI (direct cap) | ✅ | **CORE** | Trailing-12; **Argus uses forward NOI (year N+1)** — Phase 2 fix |
| Going-out / exit cap rate | ✅ | **CORE** | `exit_cap_rate` |
| Selling costs % | ✅ | **CORE** | `sale_costs_pct` |
| Gross sale price → net sale → loan payoff → equity proceeds | ✅ | **CORE** | |
| Forward NOI (year N+1) for cap | ❌ | **CORE** | Phase 2 — known accuracy gap |
| Term & Reversion valuation method (EMEA) | ❌ | *long-tail* | Phase 3+ |
| Hardcore Valuation (EMEA) | ❌ | *long-tail* | Phase 3+ |
| Initial Yield (EMEA) | ❌ | *long-tail* | Phase 3+ |
| Multiple resale calculations per property | ❌ | *long-tail* | Phase 3 |

### 11. Returns / Valuation

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Unlevered IRR | ✅ | **CORE** | |
| Levered IRR | ✅ | **CORE** | |
| Unlevered + levered equity multiple | ✅ | **CORE** | |
| NPV with primary discount rate | ❌ | STD | Trivial to add |
| Cash-on-cash year-by-year | ❌ | STD | Phase 2 |
| Leveraged / unleveraged discount rate sensitivity | ❌ | STD | Phase 2 (sensitivity matrix) |

### 12. Equity / Ownership / Waterfalls

**Argus itself offloads this to ARGUS Taliance. Most practitioners use Excel.**

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| GP / LP partners | ❌ | STD | Phase 3 — wedge opportunity (Argus AE doesn't ship this) |
| Preferred return | ❌ | STD | Phase 3 |
| Promote tiers / IRR hurdles | ❌ | STD | Phase 3 |
| Capital call schedule | ❌ | *long-tail* | Phase 3 |

### 13. Reports

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Cash Flow report | ✅ | **CORE** | `result.cashflows` DataFrame |
| Reversion summary | ✅ | **CORE** | `result.reversion` |
| Schedule of Cash Flow from Operations | 🟡 | **CORE** | Have data; need formatter |
| Assumptions report | ❌ | STD | Phase 2 |
| Lease Audit report (per-lease driver breakdown) | ❌ | **CORE** | Phase 2 — heavily praised in reviews |
| Recovery Audit report | ❌ | **CORE** | Phase 2 |
| Tenant Cash Flow report (per-tenant breakdown) | ❌ | STD | Phase 2 |
| Executive Summary | ❌ | STD | Phase 2 |
| Partition reports | ❌ | STD | Phase 3 (Argus DCF legacy) |

### 14. Sensitivity / Scenarios

**All ❌ — Phase 2 priority.**

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Sensitivity Matrix (IRR vs cap rate × growth rate, etc.) | ❌ | **CORE** | Phase 2 |
| IRR Matrix report | ❌ | **CORE** | Phase 2 |
| Scenario manager (store, compare scenarios) | ❌ | **CORE** | Phase 2 |
| Side-by-side comparison up to 5 scenarios | ❌ | STD | Phase 3 |
| Best-case / worst-case quick toggle | ❌ | STD | Phase 3 |
| Batch Update (apply changes across properties/scenarios) | ❌ | STD | Phase 3 (with portfolio) |
| Configurable & exportable reports | ❌ | STD | Phase 3 |

### 15. Portfolio / Multi-Property

**All ❌ — Phase 3 priority.**

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Portfolio holding many properties | ❌ | **CORE** | Phase 3 |
| Portfolio Cash Flow rollup | ❌ | **CORE** | Phase 3 |
| Portfolio-level scenarios | ❌ | STD | Phase 3 |
| KPI dashboard | ❌ | STD | Phase 3 |
| Hold/Sell analysis at portfolio level | ❌ | STD | Phase 3 |
| Property Resale matrix (IRR by sale year) | ❌ | **CORE** | Phase 2 — single-property |
| Mixed-use rollup (one building, multiple property types) | ❌ | STD | Phase 3 |

### 16. Imports / Exports / Integration

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| CSV / Excel rent roll import | ❌ | **CORE** | **Phase 2 — adoption blocker** |
| `.aeex` Argus export import | ❌ | **CORE** | Phase 2 — public XML schema, tolerated parsing |
| `.aeix` Argus import format | ❌ | STD | Phase 2 (same parsing work) |
| `.avux` Argus file (ZIP + XML inside) | ❌ | STD | Phase 2 (decompress to .aeix) |
| XL4ADW / Excel direct write | ❌ | *long-tail* | Phase 3 |
| Yardi Voyager / property mgmt connector | ❌ | *long-tail* | Phase 3+ |
| REST API | ❌ | STD | Phase 3 |

### 17. Inflation

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| General inflation rate | ❌ | **CORE** | Phase 2 (with per-category OpEx) |
| Per-category inflation overrides | ❌ | **CORE** | Phase 2 |
| Market rent inflation | ❌ | **CORE** | Phase 2 (MLAs) |
| CPI compound vs simple | ❌ | STD | Phase 2 |
| Per-year override vectors | ❌ | STD | Phase 2 |

### 18. Data Validation / Workflow / Access

| Feature | Coverage | Priority | Notes |
|---|---|---|---|
| Pydantic validation (structural) | ✅ | STD | Pre-build error vs Argus's runtime "Audit Log" |
| Audit Log (track edits, users) | ❌ | STD | Phase 3 (multi-user) |
| Role-based permissions | ❌ | *long-tail* | Phase 3+ |
| Property check-out / check-in lock | ❌ | *long-tail* | Phase 3+ |
| Discard Changes (rollback since save) | ❌ | *long-tail* | Phase 3 |
| Model version history | ❌ | STD | Phase 3 (git, arguably) |

---

## Phase-by-phase summary

### Phase 1 (shipped, v0.1.0)
~25 CORE features delivered: lease model, NNN/MG/FSG recoveries with caps, debt with IO and balloon, NOI assembly, reversion (trailing-12), unlevered + levered IRR, equity multiple, rent steps, free rent, TI/LC, multi-tenant rollup.

### Phase 2 (next, target v0.2.x)
**~20 features. Goal: serious-Argus-alternative parity.**
1. Forward NOI for reversion (accuracy fix)
2. Market Leasing Assumptions on rollover — full module
3. CSV/Excel rent roll import
4. `.aeex` / `.aeix` / `.avux` import (Altus XML schema)
5. General Vacancy + A&T Vacancy
6. Per-category OpEx with inflation rates
7. % of EGI OpEx line items (mgmt fees)
8. Percentage rent projection (data model already in place)
9. Recovery: Fixed Amount, Fixed Amount/Area, % Recoverable override, Gross-Up
10. Multiple debt tranches + refinance
11. Sensitivity Matrix (IRR × cap × growth)
12. IRR-by-year hold/sell matrix
13. Cash-on-cash report
14. Lease Audit + Recovery Audit reports
15. NPV with discount rate
16. Forbury-style PDF rent-roll OCR (if we want to chase that)

### Phase 3+ (parity push, target v0.3+)
- Portfolio rollup, multi-property scenarios
- Equity waterfalls (GP/LP, pref, promote) — wedge opportunity vs core AE
- Scenario Manager UI
- Audit Log, role-based permissions
- Variable interest rate, mezz debt
- EMEA valuation methods (Term & Reversion, Hardcore, Initial Yield)
- Property Classifications, Chart of Accounts hierarchy
- Multi-currency
- Yardi / property-mgmt connectors

---

## Source mention counts (top 30 features)

Ranked by triangulation strength (count of distinct agents that surfaced the feature):

| Rank | Feature | XML | Competitor | Training | YouTube | Total |
|---|---|---|---|---|---|---|
| 1 | Lease-by-lease cashflow / rent roll | ✓ | ✓ | ✓ | ✓ | 4 |
| 2 | Market Leasing Assumptions | ✓ | ✓ | ✓ | ✓ | 4 |
| 3 | Expense recoveries (NNN/MG/FSG/BYS) | ✓ | ✓ | ✓ | ✓ | 4 |
| 4 | DCF / unlevered + levered IRR | ✓ | ✓ | ✓ | ✓ | 4 |
| 5 | Debt modeling (IO + amort + refi) | ✓ | ✓ | ✓ | ✓ | 4 |
| 6 | Reversion (cap rate × NOI) | ✓ | ✓ | ✓ | ✓ | 4 |
| 7 | TI / LC (new vs renewal) | ✓ | ✓ | ✓ | — | 3 |
| 8 | Free rent / abatements | ✓ | ✓ | ✓ | — | 3 |
| 9 | Rent steps / escalations / CPI | ✓ | ✓ | ✓ | — | 3 |
| 10 | Sensitivity Matrix | ✓ | ✓ | ✓ | ✓ | 4 |
| 11 | Operating Expenses (fixed/variable) | ✓ | ✓ | ✓ | ✓ | 4 |
| 12 | Percentage Rent | ✓ | ✓ | ✓ | ✓ | 4 |
| 13 | General Vacancy + A&T Vacancy | ✓ | — | ✓ | — | 2 |
| 14 | Gross-Up % | ✓ | ✓ | ✓ | — | 3 |
| 15 | Recovery caps (Max Ceiling) | ✓ | ✓ | ✓ | — | 3 |
| 16 | Reports — Cash Flow + Assumptions | ✓ | ✓ | ✓ | ✓ | 4 |
| 17 | Lease Audit / Recovery Audit | ✓ | ✓ | ✓ | — | 3 |
| 18 | Portfolio rollup | ✓ | ✓ | ✓ | ✓ | 4 |
| 19 | Scenario Manager | ✓ | ✓ | ✓ | — | 3 |
| 20 | CapEx schedule | ✓ | ✓ | ✓ | — | 3 |
| 21 | Inflation rates per category | ✓ | — | ✓ | — | 2 |
| 22 | Sources & Uses | — | — | — | ✓ | 1 |
| 23 | Disposition assumptions | ✓ | ✓ | — | ✓ | 3 |
| 24 | Waterfall (Taliance) | — | ✓ | ✓ | ✓ | 3 |
| 25 | Multifamily Unit Mix | — | — | — | ✓ | 1 |
| 26 | Tenant Groups + Apply-to-Tenants | ✓ | — | ✓ | — | 2 |
| 27 | Batch Update | ✓ | ✓ | ✓ | ✓ | 4 |
| 28 | `.avux` / `.aeex` / `.aeix` import | ✓ | ✓ | — | ✓ | 3 |
| 29 | Audit Log | ✓ | ✓ | ✓ | — | 3 |
| 30 | Multi-currency / EMEA valuation | ✓ | ✓ | ✓ | — | 3 |

## What's NOT in Argus (wedge opportunities for OpenVal)

- **Full equity waterfall in the same tool** (Argus offloads to Taliance). Apers explicitly flags this as a gap. Building it native to OpenVal is a real differentiator.
- **Multi-tranche debt sizing** with sensitivity (Apers note). Stretch.
- **LIHTC / tax credit / opportunity zone / 1031** modeling (Apers note). Stretch.
- **Programmatic API for end-to-end underwriting automation** — Argus's API is partner-focused, not end-customer scriptable. OpenVal is Python-first, so this is built-in.

## Strategic context

As of 2026, **Argus Enterprise is being sunset as a standalone product** — Altus is migrating subscribers to ARGUS Intelligence Platform. This creates churn risk for Altus and adoption opportunity for alternatives. Source: multiple Altus marketing pages and YouTube playlist titles ("ARGUS Enterprise is now part of ARGUS Intelligence", AE 12.1 marked as the last AE-branded release).

## Sources & artifacts

- Altus official: 2-Day Training Agenda, Cert Prep Class PDF, eLearning Beginner Package, EMEA eLearning, ARGUS Tips & Tricks (Sensitivity, Batch Update)
- Schema: Scribd AE 11.0.5 XML Integration, Yumpu 9.1 XML
- Competitors: Rockport VAL, Forbury, Apers, Lightbox CashFlow, Assess+RE, PropertyMetrics, SoftwareFinder, SourceForge
- Practitioner: ACG Pro (Tricks/Traps), Realogic (Best Practices), Ask Haley, Wall Street Oasis (9 threads)
- Education: MIT OCW 11.431, JR DeLisle Tutorials, Quizlet AE Flashcards, UCLA Extension MGMT-X 47795, Ruby Shi LinkedIn cert guide
- YouTube: 14 channels/playlists, 253 raw titles, 162 unique; raw files at `/tmp/argus_titles/`
- Jobs: ZipRecruiter, Glassdoor (82 listings), Indeed (100+), SelectLeaders, Bullpen Talent
