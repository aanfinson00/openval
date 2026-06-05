import type { PropertyPayload } from "./seed";

/**
 * POST the current Property to /api/export_workbook and trigger a
 * browser download of the returned .xlsx.
 */
export async function downloadWorkbook(payload: PropertyPayload): Promise<void> {
  const res = await fetch("/api/export_workbook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(
      `${errBody.error}${errBody.detail ? `: ${errBody.detail}` : ""}`
    );
  }
  const blob = await res.blob();

  const cd = res.headers.get("Content-Disposition") || "";
  const match = cd.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? "openval-workbook.xlsx";

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
