# vnpy_rpc (Optional) - Workbench Live Trading Connector

Workbench supports an optional "vnpy_rpc" live trading provider. This mode connects to an external process via vn.py's RPC layer (ZeroMQ).

Notes:
- Default provider is `sim` and works without vn.py RPC.
- `vnpy_rpc` requires extra dependencies and a running RPC server process.

## 1) Install optional deps

```powershell
pip install -r workbench/requirements.txt -r workbench/requirements_vnpy_rpc.txt
```

## 2) Start an RPC server (demo)

In one terminal:

```powershell
python scripts/vnpy_rpc_demo_server.py
```

This binds:
- REQ/REP: `tcp://127.0.0.1:2014`
- PUB/SUB: `tcp://127.0.0.1:2015`

## 3) Start Workbench with vnpy_rpc enabled

In another terminal:

```powershell
$env:LIVE_TRADING_PROVIDER = "vnpy_rpc"
$env:VNPY_RPC_REQ = "tcp://127.0.0.1:2014"
$env:VNPY_RPC_SUB = "tcp://127.0.0.1:2015"
python -m workbench
```

## 4) Verify from API

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/live/info
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/live/ping -ContentType "application/json" -Body "{}"
```

If `pyzmq` is missing or the RPC server is not reachable, endpoints return `409 LIVE_NOT_AVAILABLE`.

