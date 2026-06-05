import type { PropertyPayload } from "./seed";

export type ReportRow = {
  label: string;
  indent: number;
  is_header: boolean;
  values: Array<number | null>;
};

export type DealSummary = {
  unlevered_irr: number | null;
  levered_irr: number | null;
  unlevered_equity_multiple: number | null;
  levered_equity_multiple: number | null;
  going_in_cap: number | null;
  stabilized_cap: number | null;
  stabilized_noi: number | null;
};

export type CashflowReport = {
  property_name: string;
  years: string[];
  rows: ReportRow[];
  summary?: DealSummary;
};

export type ErrorResponse = {
  error: string;
  detail?: string;
};

export async function fetchCashflow(
  payload: PropertyPayload,
  signal?: AbortSignal
): Promise<CashflowReport> {
  const res = await fetch("/api/cashflow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const body = await res.json();
  if (!res.ok) {
    const err = body as ErrorResponse;
    throw new Error(`${err.error}${err.detail ? `: ${err.detail}` : ""}`);
  }
  return body as CashflowReport;
}
