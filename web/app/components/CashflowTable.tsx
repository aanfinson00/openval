"use client";

import type { CashflowReport } from "@/lib/api";

type Props = {
  report: CashflowReport | null;
  loading: boolean;
  error: string | null;
};

const fmt = (n: number | null): string => {
  if (n === null) return "";
  const abs = Math.abs(n);
  if (abs < 0.5) return "0";
  const sign = n < 0 ? "(" : "";
  const close = n < 0 ? ")" : "";
  return `${sign}${Math.round(abs).toLocaleString("en-US")}${close}`;
};

export function CashflowTable({ report, loading, error }: Props) {
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
      <h1 className="text-lg font-semibold mb-1">{report.property_name}</h1>
      <p className="text-xs text-slate-500 mb-3">
        Argus-style Cash Flow report · fiscal years anchored on the acquisition month.
        {loading && <span className="ml-2 italic">refreshing…</span>}
      </p>
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

function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex items-center justify-center text-sm text-slate-500">
      {children}
    </div>
  );
}
