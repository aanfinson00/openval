"use client";

import type { CashflowReport, DealSummary, Frequency } from "@/lib/api";

type Props = {
  report: CashflowReport | null;
  loading: boolean;
  error: string | null;
  frequency: Frequency;
  onFrequencyChange: (next: Frequency) => void;
};

const fmt = (n: number | null): string => {
  if (n === null) return "";
  const abs = Math.abs(n);
  if (abs < 0.5) return "0";
  const sign = n < 0 ? "(" : "";
  const close = n < 0 ? ")" : "";
  return `${sign}${Math.round(abs).toLocaleString("en-US")}${close}`;
};

export function CashflowTable({
  report,
  loading,
  error,
  frequency,
  onFrequencyChange,
}: Props) {
  if (loading && !report) {
    return <Placeholder>Running OpenVal…</Placeholder>;
  }
  if (error) {
    return (
      <Placeholder>
        <span className="text-red-600">Error:</span> {error}
      </Placeholder>
    );
  }
  if (!report) {
    return <Placeholder>No report yet.</Placeholder>;
  }

  return (
    <div className="overflow-auto h-full p-4">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-lg font-semibold">{report.property_name}</h1>
        <FrequencyToggle value={frequency} onChange={onFrequencyChange} />
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Argus-style Cash Flow report ·{" "}
        {frequency === "monthly"
          ? "monthly columns (engine-native grain)"
          : "fiscal years anchored on the acquisition month"}
        .
        {loading && <span className="ml-2 italic">refreshing…</span>}
      </p>
      {report.summary && <SummaryHeader summary={report.summary} />}
      <table className="w-full text-xs font-mono border-collapse">
        <thead>
          <tr className="border-b border-slate-300 dark:border-slate-700">
            <th className="text-left py-1 pr-4 sticky left-0 bg-white dark:bg-slate-950">
              Line item
            </th>
            {report.years.map((y) => (
              <th key={y} className="text-right py-1 px-2 whitespace-nowrap">
                {y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.rows.map((row, idx) => (
            <tr
              key={`${row.label}-${idx}`}
              className={`${
                row.is_header
                  ? "font-semibold text-slate-700 dark:text-slate-300"
                  : ""
              } ${
                isMajorTotal(row.label) && !row.is_header
                  ? "border-t border-slate-200 dark:border-slate-800 font-semibold"
                  : ""
              }`}
            >
              <td
                className="py-0.5 pr-4 sticky left-0 bg-white dark:bg-slate-950 whitespace-nowrap"
                style={{ paddingLeft: `${row.indent * 16}px` }}
              >
                {row.label}
              </td>
              {row.values.map((v, i) => (
                <td
                  key={i}
                  className="text-right py-0.5 px-2 tabular-nums whitespace-nowrap"
                >
                  {fmt(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isMajorTotal(label: string): boolean {
  return [
    "Total Rental Revenue",
    "Total Other Tenant Revenue",
    "Total Tenant Revenue",
    "Potential Gross Revenue",
    "Total Vacancy & Credit Loss",
    "Effective Gross Revenue",
    "Total Operating Expenses",
    "Net Operating Income",
    "Total Capital Expenditures",
    "Total Leasing & Capital Costs",
    "Cash Flow Before Debt Service",
    "Cash Flow Available for Distribution",
  ].includes(label);
}

function FrequencyToggle({
  value,
  onChange,
}: {
  value: Frequency;
  onChange: (next: Frequency) => void;
}) {
  return (
    <div className="inline-flex border border-slate-300 dark:border-slate-700 rounded text-xs overflow-hidden">
      {(["annual", "monthly"] as Frequency[]).map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`px-2 py-1 ${
            value === opt
              ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
              : "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
          }`}
        >
          {opt === "annual" ? "Annual" : "Monthly"}
        </button>
      ))}
    </div>
  );
}

function SummaryHeader({ summary }: { summary: DealSummary }) {
  const tiles: Array<{ label: string; value: string }> = [
    { label: "Unlev. IRR", value: pct(summary.unlevered_irr) },
    { label: "Lev. IRR", value: pct(summary.levered_irr) },
    { label: "Unlev. EM", value: x(summary.unlevered_equity_multiple) },
    { label: "Lev. EM", value: x(summary.levered_equity_multiple) },
    { label: "Going-in Cap", value: pct(summary.going_in_cap) },
    { label: "Stabilized Cap", value: pct(summary.stabilized_cap) },
  ];
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-4">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="border border-slate-200 dark:border-slate-700 rounded px-2 py-1.5 bg-slate-50 dark:bg-slate-900"
        >
          <div className="text-[10px] uppercase tracking-wide text-slate-500">{t.label}</div>
          <div className="text-sm font-mono tabular-nums">{t.value}</div>
        </div>
      ))}
    </div>
  );
}

function pct(n: number | null): string {
  if (n === null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function x(n: number | null): string {
  if (n === null || Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}x`;
}

function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex items-center justify-center text-sm text-slate-500">
      {children}
    </div>
  );
}
