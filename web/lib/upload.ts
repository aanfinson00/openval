import type { PropertyPayload } from "./seed";

export type UploadError = {
  error: string;
  detail?: string;
};

export async function uploadWorkbook(file: File): Promise<PropertyPayload> {
  const bytes = await file.arrayBuffer();
  const res = await fetch("/api/parse_workbook", {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: bytes,
  });
  const body = await res.json();
  if (!res.ok) {
    const err = body as UploadError;
    throw new Error(`${err.error}${err.detail ? `: ${err.detail}` : ""}`);
  }
  return body as PropertyPayload;
}
