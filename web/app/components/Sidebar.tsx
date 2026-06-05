"use client";

import { useMemo, useState } from "react";
import type { PropertyPayload } from "@/lib/seed";
import { downloadWorkbook } from "@/lib/download";
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
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const activeSection = useMemo(
    () => SECTIONS.find((s) => s.key === active)!,
    [active]
  );

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
