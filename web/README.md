# OpenVal web

A browser interface for the OpenVal underwriting engine. Mirrors Argus
Enterprise's "Cash Flow" report layout: edit deal inputs in the left
sidebar, watch the cashflow update on the right.

## Stack

- **Frontend:** Next.js 14 (App Router) + Tailwind CSS
- **API:** Python serverless function (`api/cashflow.py`) that imports
  `openval` from the repo root's `src/` and returns the
  `argus_cashflow_report` output as JSON
- **Deploy target:** Vercel

## Run locally

You need Python deps (already installed in the project's `.venv`) plus
the JS deps:

```bash
cd web
npm install
npm run dev
```

That gives you the Next.js dev server at <http://localhost:3000>.

For the Python serverless function in local mode, use `vercel dev` from
the `web/` directory:

```bash
cd web
npx vercel dev
```

`vercel dev` proxies `/api/*` to the Python function and `/*` to the
Next.js dev server. First run will ask you to link the project to a
Vercel team.

## Architecture

```
web/
├── api/
│   ├── _lib.py            # pure Python — build_cashflow_report(dict) -> dict
│   ├── cashflow.py        # Vercel serverless handler wrapping _lib
│   └── requirements.txt   # Python deps for the serverless function
├── app/
│   ├── layout.tsx         # root layout
│   ├── page.tsx           # the page (sidebar + cashflow main panel)
│   ├── globals.css        # Tailwind base
│   └── components/
│       ├── Sidebar.tsx    # input tabs (currently: property / timing / vacancy)
│       └── CashflowTable.tsx  # the Argus block renderer
├── lib/
│   ├── api.ts             # client for /api/cashflow
│   └── seed.ts            # Unbound Gateway Phase I seed payload
├── vercel.json            # Python runtime + includeFiles glob for openval src
└── README.md              # this file
```

## How the Python function finds openval

`web/api/_lib.py` adds `../src` to `sys.path` so `import openval` works
both during local pytest runs and when deployed. `vercel.json` uses
`includeFiles: "../src/openval/**"` so the openval source is bundled
into the function's deploy artifact.

## Deploy

```bash
cd web
npx vercel
```

First invocation links the project. Subsequent deploys are just
`npx vercel --prod` from the same directory.

## Roadmap

- Iter I — File upload (OpenVal `.xlsx` workbook format → populates the
  sidebar). Drag-and-drop on the page.
- Iter J — Excel export. "Download as workbook" button streams a fresh
  `.xlsx` built from the current sidebar state.
