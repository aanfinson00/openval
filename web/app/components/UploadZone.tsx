"use client";

import { useCallback, useRef, useState } from "react";
import { uploadWorkbook } from "@/lib/upload";
import type { PropertyPayload } from "@/lib/seed";

type Props = {
  onLoaded: (payload: PropertyPayload) => void;
};

export function UploadZone({ onLoaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isHover, setIsHover] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [errored, setErrored] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setStatus(`Parsing ${file.name}…`);
      setErrored(false);
      try {
        const payload = await uploadWorkbook(file);
        onLoaded(payload);
        setStatus(`Loaded ${file.name}`);
      } catch (e) {
        setErrored(true);
        setStatus(`Failed: ${(e as Error).message}`);
      }
    },
    [onLoaded]
  );

  return (
    <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsHover(true);
        }}
        onDragLeave={() => setIsHover(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsHover(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void handleFile(f);
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded border-2 border-dashed px-3 py-3 text-xs text-center transition-colors ${
          isHover
            ? "border-slate-700 bg-slate-100 dark:bg-slate-800"
            : "border-slate-300 dark:border-slate-700"
        }`}
      >
        <div className="font-semibold">Drop a workbook to load</div>
        <div className="text-slate-500 mt-0.5">
          OpenVal .xlsx (or click to choose)
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
        }}
      />
      {status && (
        <div
          className={`mt-1 text-xs ${
            errored ? "text-red-600" : "text-slate-500"
          }`}
        >
          {status}
        </div>
      )}
    </div>
  );
}
