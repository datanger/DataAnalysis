# DataAnalysis Workbench - Claude Code Context

## Commands

```bash
# 启动服务 (默认: http://127.0.0.1:8000)
python -m workbench

# 运行测试
pytest tests/ -v

# 代码自检 (每次代码变更后执行)
python -m pytest tests/test_health.py
```

## Project Purpose

Local-first investment workbench for A-share investors: stock radar → research → planning → portfolio → semi-automated trading.

## ⚠️ Critical: Code Self-Check Protocol

**BEFORE any code changes, you MUST verify current implementation status:**

### For Feature Questions (e.g., "Is vnpy integrated?")

1. **NEVER trust documentation** - Always search actual code
2. **Search for actual imports**: `rg "import vnpy|from vnpy"` in project root
3. **Check implementation file directly**: Read the actual service file (e.g., `workbench/services/live_trading.py:200`)
4. **Look for conditionals**: Verify if code paths are stub/simulated or real
5. **Check requirements**: `rg "vnpy" workbench/requirements.txt`

### Self-Check Command Template

```bash
# 检查模块是否真正实现
rg "from ${module}" workbench/
rg "import ${module}" workbench/

# 检查关键文件是否存在
ls workbench/services/${module}.py

# 检查是否有模拟实现
rg "class.*Sim.*Adapter" workbench/services/
rg "STUB|TODO|FIXME" workbench/services/${module}.py
```

### Recent Self-Check Results (Reference)

- **vnpy integration**: SimAdapter implemented in `live_trading.py:73-178`, VnpyRpcAdapter is RPC client stub (needs external vn.py process)
- **backtest.py**: Implements backtest engine
- **factors.py**: Implements factor calculation

## How It Works

```
User Request → FastAPI (/api/v1/*) → Service Layer → Repository → SQLite
                                              ↓
                                       Data Provider (akshare/tushare)
```

**Data flow**: `api/app.py:1-100` sets up routes, each routes to services in `workbench/services/`.

**Repository pattern** (`workbench/services/{entity}.py`): DB operations abstracted per entity.

**Providers** (`workbench/providers/`): DataSource abstraction, `akshare` default, `tushare` optional.

## Key Patterns

| Pattern | Location | Usage |
|---------|----------|-------|
| Repository class | `workbench/services/bars.py:32` | `BarsRepo.get_one()`, `BarsRepo.upsert()` |
| Service logic | `workbench/services/scoring.py:25` | `ScoringService.calculate()` |
| Provider interface | `workbench/providers/base.py:12` | `DataProvider.fetch_bars_daily()` |
| Config loading | `workbench/config.py:15` | `AppConfig.from_env()` |

**Naming**: `PascalCase` for classes, `snake_case` for files/tables/columns.

## Data Models

- **Ticker**: `symbol` (6-digit) + `exchange` (SSE/SZSE)
- **ts_code**: `600519.SH` (TuShare format)
- **vt_symbol**: `600519.SSE` (vnpy format)
- **adj**: RAW/QFQ/HFQ (复权类型)
- **date**: `YYYY-MM-DD`, **timestamp**: ISO8601

## Gotchas

1. **SQLite thread safety**: Use short-lived connections per `db/conn.py:18` instead of sharing
2. **vnpy is simulation by default**: `live_trading.py:73` SimAdapter is default, set `LIVE_TRADING_PROVIDER=vnpy_rpc` + external vn.py for real trading
3. **TuShare token required**: Set `TUSHARE_TOKEN` env var, or use `akshare` (no token, rate limited)
4. **Audit logging**: All critical ops logged to `audit_log` table - check this for debugging
5. **WAL mode**: DB uses `PRAGMA journal_mode = WAL` - don't revert
6. **Environment variables**: Config in `workbench/config.py:15`, override via `*.env` file or env vars
7. **Response format**: Always `{ ok: bool, data: any, error?: { code, message } }` per `api/app.py`

## Environment Variables

| Var | Default | Purpose |
|-----|---------|---------|
| `WORKBENCH_HOST` | 127.0.0.1 | Server host |
| `WORKBENCH_PORT` | 8000 | Server port |
| `WORKBENCH_DATA_DIR` | ./data | Data directory |
| `WORKBENCH_DB_PATH` | ./data/workbench.db | SQLite path |
| `TUSHARE_TOKEN` | - | TuShare API |
| `LIVE_TRADING_PROVIDER` | sim | sim/vnpy_rpc |
| `VNPY_RPC_REQ` | tcp://127.0.0.1:2014 | vn.py RPC req address |
| `VNPY_RPC_SUB` | tcp://127.0.0.1:2015 | vn.py RPC sub address |
