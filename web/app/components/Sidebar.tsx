"use client";

import { useMemo, useState } from "react";
import type { PropertyPayload } from "@/lib/seed";
import { downloadWorkbook } from "@/lib/download";
import { UploadZone } from "./UploadZone";

type TabKey =
  | "property"
  | "timing"
  | "leases"
  | "vacancy"
  | "opex"
  | "capex"
  | "debt"
  | "reversion";

const TABS: { key: TabKey; label: string }[] = [
  { key: "property", label: "Property" },
  { key: "timing", label: "Timing" },
  { key: "leases", label: "Leases" },
  { key: "vacancy", label: "Vacancy" },
  { key: "opex", label: "OpEx" },
  { key: "capex", label: "CapEx" },
  { key: "debt", label: "Debt" },
  { key: "reversion", label: "Reversion" },
];

type Props = {
  payload: PropertyPayload;
  onChange: (next: PropertyPayload) => void;
};

export function Sidebar({ payload, onChange }: Props) {
  const [active, setActive] = useState<TabKey>("property");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadWorkbook(payload);
    } catch (e) {
      setDownloadError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <aside className="w-96 shrink-0 border-r border-slate-200 dark:border-slate-800 h-full overflow-y-auto flex flex-col">
      <UploadZone onLoaded={onChange} />
      <div className="flex flex-wrap gap-1 p-2 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((s) => (
          <button
            key={s.key}
            onClick={() => setActive(s.key)}
            className={`text-xs px-2 py-1 rounded ${
              active === s.key
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="p-3 space-y-3 flex-1 min-h-0">
        {active === "property" && <PropertyTab payload={payload} onChange={onChange} />}
        {active === "timing" && <TimingTab payload={payload} onChange={onChange} />}
        {active === "leases" && <LeasesTab payload={payload} onChange={onChange} />}
        {active === "vacancy" && <VacancyTab payload={payload} onChange={onChange} />}
        {active === "opex" && <OpexTab payload={payload} onChange={onChange} />}
        {active === "capex" && <CapexTab payload={payload} onChange={onChange} />}
        {active === "debt" && <DebtTab payload={payload} onChange={onChange} />}
        {active === "reversion" && <ReversionTab payload={payload} onChange={onChange} />}
      </div>
      <div className="px-3 pb-3 border-t border-slate-200 dark:border-slate-800 pt-2 space-y-1">
        <button
          onClick={() => void handleDownload()}
          disabled={downloading}
          className="w-full text-xs bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded px-3 py-2 disabled:opacity-50"
        >
          {downloading ? "Building workbook…" : "Download workbook"}
        </button>
        {downloadError && (
          <div className="text-xs text-red-600">{downloadError}</div>
        )}
        <p className="text-xs text-slate-500 mt-1">
          The downloaded .xlsx round-trips: drop it back on the upload zone
          (or run <code>scripts/run_workbook.py</code> against it) to see
          baked outputs.
        </p>
      </div>
    </aside>
  );
}

// --- per-tab editors ----------------------------------------------------

function PropertyTab({ payload, onChange }: Props) {
  return (
    <>
      <TextField label="name" value={asString(payload.name)} onChange={(v) => onChange({ ...payload, name: v })} />
      <NumberField
        label="rentable_sf"
        value={asString(payload.rentable_sf)}
        onChange={(v) => onChange({ ...payload, rentable_sf: v })}
      />
      <NumberField
        label="acquisition_costs_pct"
        value={asString(payload.acquisition_costs_pct)}
        placeholder="0"
        onChange={(v) => onChange({ ...payload, acquisition_costs_pct: v })}
      />
    </>
  );
}

function TimingTab({ payload, onChange }: Props) {
  return (
    <>
      <TextField
        label="acquisition_date"
        placeholder="YYYY-MM-DD"
        value={asString(payload.acquisition_date)}
        onChange={(v) => onChange({ ...payload, acquisition_date: v })}
      />
      <NumberField
        label="acquisition_price"
        value={asString(payload.acquisition_price)}
        onChange={(v) => onChange({ ...payload, acquisition_price: v })}
      />
      <NumberField
        label="hold_years"
        value={asString(payload.hold_years)}
        onChange={(v) => onChange({ ...payload, hold_years: Number(v) })}
      />
    </>
  );
}

function ReversionTab({ payload, onChange }: Props) {
  return (
    <>
      <NumberField
        label="exit_cap_rate"
        value={asString(payload.exit_cap_rate)}
        onChange={(v) => onChange({ ...payload, exit_cap_rate: v })}
      />
      <NumberField
        label="sale_costs_pct"
        placeholder="0.02"
        value={asString(payload.sale_costs_pct)}
        onChange={(v) => onChange({ ...payload, sale_costs_pct: v })}
      />
      <SelectField
        label="reversion_basis"
        value={asString(payload.reversion_basis) || "trailing"}
        options={["trailing", "forward"]}
        onChange={(v) => onChange({ ...payload, reversion_basis: v })}
      />
    </>
  );
}

function VacancyTab({ payload, onChange }: Props) {
  return (
    <>
      <NumberField
        label="general_vacancy_pct (flat)"
        value={asString(payload.general_vacancy_pct)}
        onChange={(v) => onChange({ ...payload, general_vacancy_pct: v })}
      />
      <NumberField
        label="credit_loss_pct (flat)"
        value={asString(payload.credit_loss_pct)}
        onChange={(v) => onChange({ ...payload, credit_loss_pct: v })}
      />
      <YearMapEditor
        title="general_vacancy_by_year"
        map={(payload.general_vacancy_by_year as Record<string, unknown>) || {}}
        onChange={(next) => onChange({ ...payload, general_vacancy_by_year: next })}
      />
      <YearMapEditor
        title="credit_loss_by_year"
        map={(payload.credit_loss_by_year as Record<string, unknown>) || {}}
        onChange={(next) => onChange({ ...payload, credit_loss_by_year: next })}
      />
    </>
  );
}

function OpexTab({ payload, onChange }: Props) {
  return (
    <CategoryMatrixEditor
      title="opex_categories"
      categories={(payload.opex_categories as Record<string, Record<string, unknown>>) || {}}
      defaultCategories={["Real Estate Taxes", "Insurance", "Property Management Fee", "CAM"]}
      onChange={(next) => onChange({ ...payload, opex_categories: next })}
    />
  );
}

function DebtTab({ payload, onChange }: Props) {
  const loan = (payload.loan as Record<string, unknown> | undefined) || null;
  const refinance = (payload.refinance as Record<string, unknown> | undefined) || null;

  const setLoan = (next: Record<string, unknown> | null) =>
    onChange({ ...payload, loan: next });
  const setRefi = (next: Record<string, unknown> | null) =>
    onChange({ ...payload, refinance: next });

  return (
    <div className="space-y-3">
      {loan ? (
        <div className="border border-slate-200 dark:border-slate-700 rounded p-2 space-y-2">
          <div className="text-xs uppercase tracking-wide text-slate-500">Loan</div>
          <NumberField label="principal" value={asString(loan.principal)} onChange={(v) => setLoan({ ...loan, principal: v })} />
          <NumberField label="rate_annual" value={asString(loan.rate_annual)} onChange={(v) => setLoan({ ...loan, rate_annual: v })} />
          <div className="grid grid-cols-2 gap-2">
            <NumberField label="amortization_years" value={asString(loan.amortization_years)} onChange={(v) => setLoan({ ...loan, amortization_years: Number(v) })} />
            <NumberField label="term_years" value={asString(loan.term_years)} onChange={(v) => setLoan({ ...loan, term_years: Number(v) })} />
            <NumberField label="interest_only_years" value={asString(loan.interest_only_years)} onChange={(v) => setLoan({ ...loan, interest_only_years: Number(v) })} />
          </div>
          <button
            onClick={() => setLoan(null)}
            className="w-full text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
          >
            Remove loan
          </button>
        </div>
      ) : (
        <button
          onClick={() =>
            setLoan({
              principal: "1000000",
              rate_annual: "0.06",
              amortization_years: 30,
              term_years: 10,
              interest_only_years: 0,
            })
          }
          className="w-full text-xs px-2 py-1 rounded border border-dashed border-emerald-400 text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950"
        >
          + Add loan
        </button>
      )}

      {refinance ? (
        <div className="border border-slate-200 dark:border-slate-700 rounded p-2 space-y-2">
          <div className="text-xs uppercase tracking-wide text-slate-500">Mid-hold refinance</div>
          <TextField label="effective_date" placeholder="YYYY-MM-DD" value={asString(refinance.effective_date)} onChange={(v) => setRefi({ ...refinance, effective_date: v })} />
          <NumberField label="prepayment_penalty_pct" value={asString(refinance.prepayment_penalty_pct)} onChange={(v) => setRefi({ ...refinance, prepayment_penalty_pct: v })} />
          <div className="border-t border-slate-200 dark:border-slate-700 pt-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">new_loan</div>
            <NewLoanFields
              loan={(refinance.new_loan as Record<string, unknown>) || {}}
              onChange={(nl) => setRefi({ ...refinance, new_loan: nl })}
            />
          </div>
          <button
            onClick={() => setRefi(null)}
            className="w-full text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
          >
            Remove refinance
          </button>
        </div>
      ) : (
        <button
          onClick={() =>
            setRefi({
              effective_date: "2030-01-01",
              prepayment_penalty_pct: "0",
              new_loan: {
                principal: "1500000",
                rate_annual: "0.055",
                amortization_years: 30,
                term_years: 10,
                interest_only_years: 0,
              },
            })
          }
          className="w-full text-xs px-2 py-1 rounded border border-dashed border-emerald-400 text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950"
        >
          + Add refinance
        </button>
      )}
    </div>
  );
}

function NewLoanFields({
  loan,
  onChange,
}: {
  loan: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <NumberField label="principal" value={asString(loan.principal)} onChange={(v) => onChange({ ...loan, principal: v })} />
      <NumberField label="rate_annual" value={asString(loan.rate_annual)} onChange={(v) => onChange({ ...loan, rate_annual: v })} />
      <NumberField label="amortization_years" value={asString(loan.amortization_years)} onChange={(v) => onChange({ ...loan, amortization_years: Number(v) })} />
      <NumberField label="term_years" value={asString(loan.term_years)} onChange={(v) => onChange({ ...loan, term_years: Number(v) })} />
      <NumberField label="interest_only_years" value={asString(loan.interest_only_years)} onChange={(v) => onChange({ ...loan, interest_only_years: Number(v) })} />
    </div>
  );
}

function CapexTab({ payload, onChange }: Props) {
  return (
    <CategoryMatrixEditor
      title="capex_categories"
      categories={(payload.capex_categories as Record<string, Record<string, unknown>>) || {}}
      defaultCategories={["Capital Reserves", "Non-Leasing Capital Expense"]}
      onChange={(next) => onChange({ ...payload, capex_categories: next })}
    />
  );
}

// --- Leases tab ---------------------------------------------------------

type LeaseRow = Record<string, unknown>;

function LeasesTab({ payload, onChange }: Props) {
  const leases = useMemo<LeaseRow[]>(
    () => (Array.isArray(payload.leases) ? (payload.leases as LeaseRow[]) : []),
    [payload]
  );
  const [openIdx, setOpenIdx] = useState<number>(0);

  const setLease = (idx: number, next: LeaseRow) => {
    const copy = leases.slice();
    copy[idx] = next;
    onChange({ ...payload, leases: copy });
  };
  const removeLease = (idx: number) => {
    const copy = leases.slice();
    copy.splice(idx, 1);
    onChange({ ...payload, leases: copy });
    if (openIdx >= copy.length) setOpenIdx(Math.max(0, copy.length - 1));
  };
  const addLease = () => {
    const next: LeaseRow = {
      suite_id: String(leases.length + 1).padStart(3, "0"),
      tenant_name: "New Tenant",
      area_sf: 1,
      start_date: asString(payload.acquisition_date) || "2026-01-01",
      end_date: "2031-01-01",
      base_rent_steps: [{ start_date: "2026-01-01", annual_psf: "0" }],
      free_rent_months: 0,
      ti_psf: "0",
      lc_pct_first_year_rent: "0",
      expense_structure: "NNN",
    };
    onChange({ ...payload, leases: [...leases, next] });
    setOpenIdx(leases.length);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-slate-500">
          {leases.length} lease{leases.length === 1 ? "" : "s"}
        </div>
        <button
          onClick={addLease}
          className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
        >
          + Add lease
        </button>
      </div>
      {leases.length === 0 && (
        <div className="text-xs text-slate-500 italic">
          No leases. Click "+ Add lease" to model a tenant.
        </div>
      )}
      {leases.map((lease, idx) => (
        <div
          key={idx}
          className="border border-slate-200 dark:border-slate-700 rounded"
        >
          <button
            onClick={() => setOpenIdx(openIdx === idx ? -1 : idx)}
            className="w-full text-left px-2 py-1.5 text-xs flex items-center justify-between bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-t"
          >
            <span className="font-medium">
              #{asString(lease.suite_id) || idx + 1} · {asString(lease.tenant_name) || "(unnamed)"}
            </span>
            <span className="text-slate-400">{openIdx === idx ? "▾" : "▸"}</span>
          </button>
          {openIdx === idx && (
            <LeaseEditor
              lease={lease}
              onChange={(next) => setLease(idx, next)}
              onRemove={() => removeLease(idx)}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function LeaseEditor({
  lease,
  onChange,
  onRemove,
}: {
  lease: LeaseRow;
  onChange: (next: LeaseRow) => void;
  onRemove: () => void;
}) {
  const setField = (key: string, value: unknown) => onChange({ ...lease, [key]: value });

  return (
    <div className="p-2 space-y-2 border-t border-slate-200 dark:border-slate-700">
      <div className="grid grid-cols-2 gap-2">
        <TextField label="suite_id" value={asString(lease.suite_id)} onChange={(v) => setField("suite_id", v)} />
        <TextField label="tenant_name" value={asString(lease.tenant_name)} onChange={(v) => setField("tenant_name", v)} />
        <NumberField label="area_sf" value={asString(lease.area_sf)} onChange={(v) => setField("area_sf", v)} />
        <SelectField
          label="expense_structure"
          value={asString(lease.expense_structure) || "NNN"}
          options={["NNN", "MG_BASE_YEAR", "MG_EXPENSE_STOP", "FSG"]}
          onChange={(v) => setField("expense_structure", v)}
        />
        <TextField label="start_date" value={asString(lease.start_date)} onChange={(v) => setField("start_date", v)} />
        <TextField label="end_date" value={asString(lease.end_date)} onChange={(v) => setField("end_date", v)} />
        <NumberField label="free_rent_months" value={asString(lease.free_rent_months)} onChange={(v) => setField("free_rent_months", Number(v))} />
        <NumberField label="ti_psf" value={asString(lease.ti_psf)} onChange={(v) => setField("ti_psf", v)} />
        <NumberField label="lc_pct_first_year_rent" value={asString(lease.lc_pct_first_year_rent)} onChange={(v) => setField("lc_pct_first_year_rent", v)} />
      </div>
      <RentStepsEditor
        steps={(lease.base_rent_steps as Array<Record<string, unknown>>) || []}
        onChange={(next) => setField("base_rent_steps", next)}
      />
      <MlaEditor
        mla={(lease.market_leasing_assumption as Record<string, unknown> | undefined) || null}
        onChange={(next) => setField("market_leasing_assumption", next)}
      />
      <button
        onClick={onRemove}
        className="w-full text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
      >
        Remove lease
      </button>
    </div>
  );
}

function MlaEditor({
  mla,
  onChange,
}: {
  mla: Record<string, unknown> | null;
  onChange: (next: Record<string, unknown> | null) => void;
}) {
  if (!mla) {
    return (
      <button
        onClick={() =>
          onChange({
            market_rent_psf: "0",
            market_rent_growth_pct: "0.03",
            new_term_months: 120,
            rent_escalation_pct: "0.03",
            free_rent_months_new: 0,
            ti_psf_new: "0",
            lc_pct_new: "0",
            renewal_probability: "0.7",
            downtime_months_new: 0,
            expense_structure: "NNN",
          })
        }
        className="w-full text-xs px-2 py-1 rounded border border-dashed border-emerald-400 text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950"
      >
        + Add Market Leasing Assumption
      </button>
    );
  }
  const set = (key: string, value: unknown) => onChange({ ...mla, [key]: value });
  return (
    <div className="border border-emerald-200 dark:border-emerald-900 rounded p-2 space-y-2 bg-emerald-50/50 dark:bg-emerald-950/30">
      <div className="text-[10px] uppercase tracking-wide text-emerald-700 dark:text-emerald-300 font-semibold">
        Market Leasing Assumption — applies on rollover
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NumberField label="market_rent_psf" value={asString(mla.market_rent_psf)} onChange={(v) => set("market_rent_psf", v)} />
        <NumberField label="market_rent_growth_pct" value={asString(mla.market_rent_growth_pct)} onChange={(v) => set("market_rent_growth_pct", v)} />
        <NumberField label="new_term_months" value={asString(mla.new_term_months)} onChange={(v) => set("new_term_months", Number(v))} />
        <NumberField label="rent_escalation_pct" value={asString(mla.rent_escalation_pct)} onChange={(v) => set("rent_escalation_pct", v)} />
        <NumberField label="renewal_probability" value={asString(mla.renewal_probability)} onChange={(v) => set("renewal_probability", v)} />
        <NumberField label="downtime_months_new" value={asString(mla.downtime_months_new)} onChange={(v) => set("downtime_months_new", Number(v))} />
        <NumberField label="free_rent_months_new" value={asString(mla.free_rent_months_new)} onChange={(v) => set("free_rent_months_new", Number(v))} />
        <NumberField label="free_rent_months_renewal" value={asString(mla.free_rent_months_renewal)} onChange={(v) => set("free_rent_months_renewal", Number(v))} />
        <NumberField label="ti_psf_new" value={asString(mla.ti_psf_new)} onChange={(v) => set("ti_psf_new", v)} />
        <NumberField label="ti_psf_renewal" value={asString(mla.ti_psf_renewal)} onChange={(v) => set("ti_psf_renewal", v)} />
        <NumberField label="lc_pct_new" value={asString(mla.lc_pct_new)} onChange={(v) => set("lc_pct_new", v)} />
        <NumberField label="lc_pct_renewal" value={asString(mla.lc_pct_renewal)} onChange={(v) => set("lc_pct_renewal", v)} />
        <SelectField
          label="expense_structure"
          value={asString(mla.expense_structure) || "NNN"}
          options={["NNN", "MG_BASE_YEAR", "MG_EXPENSE_STOP", "FSG"]}
          onChange={(v) => set("expense_structure", v)}
        />
      </div>
      <button
        onClick={() => onChange(null)}
        className="text-[10px] text-emerald-700 hover:text-emerald-900 underline"
      >
        remove MLA
      </button>
    </div>
  );
}

function RentStepsEditor({
  steps,
  onChange,
}: {
  steps: Array<Record<string, unknown>>;
  onChange: (next: Array<Record<string, unknown>>) => void;
}) {
  const update = (idx: number, key: string, value: string) => {
    const copy = steps.slice();
    copy[idx] = { ...copy[idx], [key]: value };
    onChange(copy);
  };
  const remove = (idx: number) => {
    const copy = steps.slice();
    copy.splice(idx, 1);
    onChange(copy);
  };
  const add = () => {
    const lastDate = steps.length ? asString(steps[steps.length - 1].start_date) : "2026-01-01";
    onChange([...steps, { start_date: lastDate, annual_psf: "0" }]);
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-slate-500">base_rent_steps</div>
        <button onClick={add} className="text-xs text-emerald-700 hover:underline">+ step</button>
      </div>
      {steps.map((step, idx) => (
        <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-1 items-center">
          <input
            className="border border-slate-300 dark:border-slate-700 rounded px-1 py-0.5 bg-white dark:bg-slate-900 text-xs"
            value={asString(step.start_date)}
            placeholder="YYYY-MM-DD"
            onChange={(e) => update(idx, "start_date", e.target.value)}
          />
          <input
            className="border border-slate-300 dark:border-slate-700 rounded px-1 py-0.5 bg-white dark:bg-slate-900 text-xs"
            value={asString(step.annual_psf)}
            placeholder="$/sf/yr"
            onChange={(e) => update(idx, "annual_psf", e.target.value)}
          />
          <button onClick={() => remove(idx)} className="text-xs text-red-500 hover:text-red-700 px-1">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

// --- year-map editor (sparse {year: value}) -----------------------------

function YearMapEditor({
  title,
  map,
  onChange,
}: {
  title: string;
  map: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const entries = Object.entries(map).sort(([a], [b]) => Number(a) - Number(b));

  const update = (year: string, value: string) => {
    onChange({ ...map, [year]: value });
  };
  const remove = (year: string) => {
    const next = { ...map };
    delete next[year];
    onChange(next);
  };
  const add = () => {
    const nextYear = entries.length
      ? String(Number(entries[entries.length - 1][0]) + 1)
      : String(new Date().getUTCFullYear());
    onChange({ ...map, [nextYear]: "0" });
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-slate-500">{title}</div>
        <button onClick={add} className="text-xs text-emerald-700 hover:underline">+ year</button>
      </div>
      {entries.length === 0 && (
        <div className="text-xs text-slate-400 italic">(empty — falls back to flat pct)</div>
      )}
      {entries.map(([year, value]) => (
        <div key={year} className="grid grid-cols-[80px_1fr_auto] gap-1 items-center">
          <div className="text-xs font-mono text-slate-700 dark:text-slate-300">{year}</div>
          <input
            className="border border-slate-300 dark:border-slate-700 rounded px-1 py-0.5 bg-white dark:bg-slate-900 text-xs"
            value={asString(value)}
            onChange={(e) => update(year, e.target.value)}
          />
          <button onClick={() => remove(year)} className="text-xs text-red-500 hover:text-red-700 px-1">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

// --- category × year matrix editor (opex / capex categories) ------------

function CategoryMatrixEditor({
  title,
  categories,
  defaultCategories,
  onChange,
}: {
  title: string;
  categories: Record<string, Record<string, unknown>>;
  defaultCategories: string[];
  onChange: (next: Record<string, Record<string, unknown>>) => void;
}) {
  const catNames = Object.keys(categories);
  const [active, setActive] = useState<string>(catNames[0] || defaultCategories[0]);

  const ensureCat = (cat: string) => {
    if (!(cat in categories)) onChange({ ...categories, [cat]: {} });
  };
  const removeCat = (cat: string) => {
    const next = { ...categories };
    delete next[cat];
    onChange(next);
    const remaining = Object.keys(next);
    if (active === cat) setActive(remaining[0] || defaultCategories[0]);
  };
  const updateCat = (cat: string, map: Record<string, unknown>) => {
    onChange({ ...categories, [cat]: map });
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-slate-500">{title}</div>
      </div>
      <div className="flex flex-wrap gap-1">
        {defaultCategories.map((cat) => (
          <button
            key={cat}
            onClick={() => {
              ensureCat(cat);
              setActive(cat);
            }}
            className={`text-[10px] px-1.5 py-0.5 rounded border ${
              active === cat && cat in categories
                ? "bg-slate-900 text-white border-slate-900"
                : cat in categories
                ? "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700"
                : "border-dashed border-slate-300 dark:border-slate-700 text-slate-400"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>
      {catNames
        .filter((c) => !defaultCategories.includes(c))
        .map((cat) => (
          <button
            key={cat}
            onClick={() => setActive(cat)}
            className={`text-[10px] px-1.5 py-0.5 rounded mr-1 ${
              active === cat
                ? "bg-slate-900 text-white"
                : "bg-slate-100 dark:bg-slate-800 text-slate-700"
            }`}
          >
            {cat}
          </button>
        ))}
      {active in categories ? (
        <>
          <YearMapEditor
            title={active}
            map={categories[active]}
            onChange={(m) => updateCat(active, m)}
          />
          <button
            onClick={() => removeCat(active)}
            className="w-full text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100"
          >
            Remove {active}
          </button>
        </>
      ) : (
        <div className="text-xs text-slate-400 italic">
          Click a category above to start editing its yearly values.
        </div>
      )}
    </div>
  );
}

// --- field primitives ---------------------------------------------------

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-xs">
      <span className="block uppercase tracking-wide text-slate-500 mb-1">{label}</span>
      <input
        className="w-full border border-slate-300 dark:border-slate-700 rounded px-2 py-1 bg-white dark:bg-slate-900 text-sm"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function NumberField(props: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  return <TextField {...props} />;
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (next: string) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="block uppercase tracking-wide text-slate-500 mb-1">{label}</span>
      <select
        className="w-full border border-slate-300 dark:border-slate-700 rounded px-2 py-1 bg-white dark:bg-slate-900 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}

function asString(v: unknown): string {
  if (v === undefined || v === null) return "";
  return String(v);
}
