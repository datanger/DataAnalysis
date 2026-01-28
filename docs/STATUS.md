# Implementation Status (as of 2026-01-24)

This repo now contains an initial Workbench backend under `workbench/` plus a minimal built-in UI served from the API.

## What Works Now

- API server: `python -m workbench`
- Built-in UI: `GET /app/` (served by FastAPI)
- SQLite migrations + local DB at `data/workbench.db` (default)
- Data ingestion tasks:
  - `ingest_instruments` (TuShare preferred if `TUSHARE_TOKEN` set; else AKShare)
  - `ingest_bars_daily` for specific symbols
  - `ingest_fundamentals_daily` (TuShare daily_basic; optional)
  - `ingest_capital_flow_daily` (TuShare moneyflow; optional)
- Stock workspace:
  - `GET /api/v1/stocks/{exchange}/{symbol}/workspace`
  - Includes bars + MA/RSI/MACD indicators + fundamentals/capital flow (if ingested) + latest score/plan + notes
- Scoring:
  - `POST /api/v1/scores/calc` (simple technical scoring v1; explainable breakdown + metrics)
- Plans/notes:
  - `POST /api/v1/plans/generate` (heuristic plan generator)
  - `POST /api/v1/notes` (markdown notes)
- Portfolio & simulation:
  - `POST/GET /api/v1/portfolios` (with local cash + positions)
  - `POST/GET/PATCH/DELETE /api/v1/order_drafts`
  - `POST /api/v1/risk/check` (basic risk rules)
  - `POST /api/v1/sim/confirm` (creates sim orders/trades, updates cash/positions)
  - `GET /api/v1/sim/orders`, `GET /api/v1/sim/trades`
- Rebalance:
  - `POST /api/v1/rebalance/suggest` (target weights -> suggested orders; optional draft creation)
- Audit:
  - key actions write audit records
  - `GET /api/v1/audit?entity_type=&entity_id=`

## Current Limitations (Expected at this Stage)

- Radar scan only scores instruments that already have enough local bars; it will skip symbols without data.
- News is still placeholder in the workspace response (schema exists; ingestion not implemented yet).
- Simulation execution is simplified (single-fill, simple fee/slippage model; no partial fills).
- No auth/multi-user (local single-user assumption).
