"use client";

import { useMemo, useState } from "react";
import type { PropertyPayload } from "@/lib/seed";
import { UploadZone } from "./UploadZone";

const SECTIONS = [
  { key: "property", label: "Property", fields: ["name", "rentable_sf"] },
  {
    key: "timing",
    label: "Timing",
    fields: ["acquisition_date", "acquisition_price", "hold_years", "exit_cap_rate"],
  },
  { key: "vacancy", label: "Vacancy", fields: ["general_vacancy_pct", "credit_loss_pct"] },
] as const;

type Props = {
  payload: PropertyPayload;
  onChange: (next: PropertyPayload) => void;
};

export function Sidebar({ payload, onChange }: Props) {
  const [active, setActive] = useState<string>(SECTIONS[0].key);

  const activeSection = useMemo(
    () => SECTIONS.find((s) => s.key === active)!,
    [active]
  );

  return (
    <aside className="w-80 shrink-0 border-r border-slate-200 dark:border-slate-800 h-full overflow-y-auto">
      <UploadZone onLoaded={onChange} />
      <div className="flex flex-wrap gap-1 p-2 border-b border-slate-200 dark:border-slate-800">
        {SECTIONS.map((s) => (
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
      <div className="p-3 space-y-3">
        {activeSection.fields.map((field) => (
          <Field
            key={field}
            field={field}
            value={(payload as Record<string, unknown>)[field]}
            onChange={(v) => onChange({ ...payload, [field]: v })}
          />
        ))}
      </div>
      <div className="px-3 pb-3 text-xs text-slate-500">
        Editing the seeded Unbound Gateway deal. Lease / OpEx / CapEx panels
        coming in iter I — for now, swap inputs in via file upload (also iter I).
      </div>
    </aside>
  );
}

function Field({
  field,
  value,
  onChange,
}: {
  field: string;
  value: unknown;
  onChange: (next: string) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="block uppercase tracking-wide text-slate-500 mb-1">
        {field}
      </span>
      <input
        className="w-full border border-slate-300 dark:border-slate-700 rounded px-2 py-1 bg-white dark:bg-slate-900 text-sm"
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
