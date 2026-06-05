"use client";

import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { CashflowTable } from "./components/CashflowTable";
import { fetchCashflow, type CashflowReport, type Frequency } from "@/lib/api";
import { unboundSeed, type PropertyPayload } from "@/lib/seed";

const STORAGE_KEY = "openval:payload:v1";

export default function Page() {
  const [payload, setPayload] = useState<PropertyPayload>(() => unboundSeed());
  const [report, setReport] = useState<CashflowReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [frequency, setFrequency] = useState<Frequency>("annual");
  const [hydrated, setHydrated] = useState(false);

  // Rehydrate from localStorage on mount (client only).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setPayload(JSON.parse(raw) as PropertyPayload);
    } catch {
      // ignore stale/corrupt entry
    }
    setHydrated(true);
  }, []);

  // Persist on every change, after hydration.
  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // quota / private-mode → silent skip
    }
  }, [payload, hydrated]);

  const resetSeed = useCallback(() => {
    const seed = unboundSeed();
    setPayload(seed);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const run = useCallback(
    async (body: PropertyPayload, freq: Frequency) => {
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      try {
        const r = await fetchCashflow(body, controller.signal, freq);
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

  // Debounced refresh on payload / frequency change. The hydration guard
  // prevents firing with the stale unboundSeed before localStorage loads.
  useEffect(() => {
    if (!hydrated) return;
    const t = setTimeout(() => {
      void run(payload, frequency);
    }, 300);
    return () => clearTimeout(t);
  }, [payload, frequency, hydrated, run]);

  return (
    <main className="h-screen flex flex-row text-slate-900 dark:text-slate-100 bg-white dark:bg-slate-950">
      <Sidebar payload={payload} onChange={setPayload} onReset={resetSeed} />
      <div className="flex-1 min-w-0">
        <CashflowTable
          report={report}
          loading={loading}
          error={error}
          frequency={frequency}
          onFrequencyChange={setFrequency}
        />
      </div>
    </main>
  );
}
