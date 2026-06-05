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
  | "reversion";

const TABS: { key: TabKey; label: string }[] = [
  { key: "property", label: "Property" },
  { key: "timing", label: "Timing" },
  { key: "leases", label: "Leases" },
  { key: "vacancy", label: "Vacancy" },
  { key: "opex", label: "OpEx" },
  { key: "capex", label: "CapEx" },
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
      <button
        onClick={onRemove}
        className="w-full text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
      >
        Remove lease
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
