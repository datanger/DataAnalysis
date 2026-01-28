# Workbench dev quickstart

## 1) Install deps

```powershell
pip install -r requirements.txt
```

## 2) (Optional) Configure TuShare

```powershell
$env:TUSHARE_TOKEN = "<your_token>"
```

## 3) Run API server

```powershell
python -m workbench
```

Server: `http://127.0.0.1:8000`

Built-in UI (minimal): `http://127.0.0.1:8000/app/`

## 4) Seed instruments (recommended)

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tasks/run `
  -ContentType 'application/json' `
  -Body '{"type":"ingest_instruments","payload":{}}'
```

## 5) Ingest daily bars for a symbol

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tasks/run `
  -ContentType 'application/json' `
  -Body '{"type":"ingest_bars_daily","payload":{"symbols":[{"symbol":"600519","exchange":"SSE"}],"start_date":"20200101"}}'
```

## 5.1) (Optional) Ingest fundamentals (TuShare required)

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tasks/run `
  -ContentType 'application/json' `
  -Body '{"type":"ingest_fundamentals_daily","payload":{"symbols":[{"symbol":"600519","exchange":"SSE"}]}}'
```

## 5.2) (Optional) Ingest capital flow (TuShare required)

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tasks/run `
  -ContentType 'application/json' `
  -Body '{"type":"ingest_capital_flow_daily","payload":{"symbols":[{"symbol":"600519","exchange":"SSE"}]}}'
```

## 6) Score + plan + note

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/scores/calc `
  -ContentType 'application/json' `
  -Body '{"symbol":"600519","exchange":"SSE"}'

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/plans/generate `
  -ContentType 'application/json' `
  -Body '{"symbol":"600519","exchange":"SSE"}'

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/notes `
  -ContentType 'application/json' `
  -Body '{"symbol":"600519","exchange":"SSE","content_md":"# 研究纪要\n\n- 示例"}'
```

## 7) Open stock workspace

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/stocks/SSE/600519/workspace
```

## 8) Create a portfolio

```powershell
$p = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/portfolios `
  -ContentType 'application/json' `
  -Body '{"name":"demo","initial_cash":500000}'
$pid = $p.data.portfolio_id
```

## 9) Rebalance suggest (targets -> drafts)

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/rebalance/suggest `
  -ContentType 'application/json' `
  -Body ("{\"portfolio_id\":\"$pid\",\"targets\":[{\"symbol\":\"600519\",\"exchange\":\"SSE\",\"weight\":1.0}],\"create_drafts\":true}")
```

## 10) Risk check + confirm (sim)

```powershell
# List drafts
$drafts = Invoke-RestMethod -Uri ("http://127.0.0.1:8000/api/v1/order_drafts?portfolio_id=$pid")
$did = $drafts.data[0].draft_id

$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/risk/check `
  -ContentType 'application/json' `
  -Body ("{\"draft_ids\":[\"$did\"]}")

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/sim/confirm `
  -ContentType 'application/json' `
  -Body ("{\"draft_ids\":[\"$did\"],\"riskcheck_id\":\"" + $r.data.riskcheck_id + "\"}")
```

## 11) Ledger

```powershell
Invoke-RestMethod -Uri ("http://127.0.0.1:8000/api/v1/sim/orders?portfolio_id=$pid")
Invoke-RestMethod -Uri ("http://127.0.0.1:8000/api/v1/sim/trades?portfolio_id=$pid")
Invoke-RestMethod -Uri ("http://127.0.0.1:8000/api/v1/portfolios/$pid")
```

## 12) (Optional) vnpy_rpc live trading provider

See `docs/VNPY_RPC.md`.
