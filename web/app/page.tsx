"use client";

import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { CashflowTable } from "./components/CashflowTable";
import { fetchCashflow, type CashflowReport } from "@/lib/api";
import { unboundSeed, type PropertyPayload } from "@/lib/seed";

export default function Page() {
  const [payload, setPayload] = useState<PropertyPayload>(() => unboundSeed());
  const [report, setReport] = useState<CashflowReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (body: PropertyPayload) => {
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      try {
        const r = await fetchCashflow(body, controller.signal);
        setReport(r);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
      return () => controller.abort();
    },
    []
  );

  useEffect(() => {
    void run(payload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounce edits so we don't hammer the API on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      void run(payload);
    }, 300);
    return () => clearTimeout(t);
  }, [payload, run]);

  return (
    <main className="h-screen flex flex-row text-slate-900 dark:text-slate-100 bg-white dark:bg-slate-950">
      <Sidebar payload={payload} onChange={setPayload} />
      <div className="flex-1 min-w-0">
        <CashflowTable report={report} loading={loading} error={error} />
      </div>
    </main>
  );
}
