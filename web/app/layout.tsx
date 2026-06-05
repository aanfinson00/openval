import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpenVal — Argus Cash Flow",
  description:
    "Open-source recreation of Argus Enterprise's Cash Flow report. Edit a deal in the sidebar; the cashflow updates live.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  );
}
