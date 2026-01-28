from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from workbench.config import load_config
from workbench.db.conn import connect
from workbench.db.migrate import apply_migrations
from workbench.errors import ErrorCodes
from workbench.providers.registry import build_registry
from workbench.services.audit import AuditLogger
from workbench.services.audit_query import AuditQueryRepo
from workbench.services.bars import BarsRepo
from workbench.services.instruments import InstrumentsRepo
from workbench.services.notes import NotesRepo
from workbench.services.order_drafts import OrderDraftRepo
from workbench.services.plan_service import PlanService
from workbench.services.plans import PlansRepo
from workbench.services.portfolios import PortfolioRepo
from workbench.services.radar import RadarRepo, RadarService
from workbench.services.rebalance import RebalanceService
from workbench.services.risk import RiskService
from workbench.services.scoring import ScoringService
from workbench.services.scores import ScoresRepo
from workbench.services.sim import LedgerRepo, SimService
from workbench.services.tasks import TaskManager
from workbench.services.watchlists import WatchlistRepo
from workbench.services.workspace import WorkspaceService
from workbench.services.fundamentals_ingest import FundamentalsIngestService
from workbench.services.capital_flow_ingest import CapitalFlowIngestService


config = load_config()

conn0 = connect(config.db_path)
try:
    apply_migrations(conn0, migrations_dir=(Path(__file__).resolve().parents[1] / "migrations"))
finally:
    conn0.close()

registry = build_registry(tushare_token=config.tushare_token)
providers = registry.ordered(config.provider_order)

task_manager = TaskManager(config.db_path, max_workers=config.max_workers)

app = FastAPI(title="Workbench API", version="0.1.0")

# Allow the Flask UI (StockAnal_Sys) to call the API from another localhost port.
# Local-first: we only allow localhost origins by regex.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Minimal built-in UI served at /app (keeps /api/* unshadowed).
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parents[1] / "web", html=True), name="app")


def api_ok(data):
    return {"ok": True, "data": data}


def api_err(code: str, message: str, details=None, *, status_code: int = 400):
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": {"code": code, "message": message, "details": details}},
    )


@app.get("/api/v1/health")
def health():
    provider_status = [p.status().__dict__ for p in providers]
    db_ok = True
    tasks = {"running": 0, "failed": 0}
    data = {"bars_latest_ingested_at": None}
    try:
        conn = connect(config.db_path)
        try:
            conn.execute("SELECT 1").fetchone()
            row = conn.execute("SELECT COUNT(1) FROM tasks WHERE status='RUNNING'").fetchone()
            tasks["running"] = int(row[0]) if row else 0
            row = conn.execute("SELECT COUNT(1) FROM tasks WHERE status='FAILED'").fetchone()
            tasks["failed"] = int(row[0]) if row else 0
            row = conn.execute("SELECT MAX(ingested_at) FROM bars_daily").fetchone()
            data["bars_latest_ingested_at"] = row[0] if row else None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        db_ok = False

    return api_ok(
        {
            "db_ok": db_ok,
            "providers": provider_status,
            "tasks": tasks,
            "data": data,
            "now": datetime.now().isoformat(timespec="seconds"),
        }
    )


@app.get("/api/v1/instruments/search")
def instruments_search(q: str, limit: int = 50):
    if not q:
        return api_err(ErrorCodes.VALIDATION_ERROR, "q is required")
    conn = connect(config.db_path)
    try:
        repo = InstrumentsRepo(conn)
        return api_ok(repo.search(q=q, limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/stocks/{exchange}/{symbol}/workspace")
def stock_workspace(exchange: str, symbol: str, adj: str = "RAW"):
    conn = connect(config.db_path)
    try:
        svc = WorkspaceService(conn)
        ws = svc.get_workspace(symbol=str(symbol).zfill(6), exchange=exchange, adj=adj)
        if not ws.get("price_bars"):
            return api_err(
                ErrorCodes.DATA_NOT_READY,
                "no market data in local db; run ingest_bars_daily first",
                {"task": "ingest_bars_daily"},
                status_code=409,
            )
        return api_ok(ws)
    finally:
        conn.close()


@app.post("/api/v1/scores/calc")
def scores_calc(body: dict):
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    adj = body.get("adj") or "RAW"
    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        svc = ScoringService(conn)
        try:
            result = svc.calc_and_persist(symbol=str(symbol).zfill(6), exchange=str(exchange), adj=str(adj))
        except ValueError as e:
            return api_err(ErrorCodes.DATA_NOT_READY, str(e), {"task": "ingest_bars_daily"}, status_code=409)

        AuditLogger(conn).log(
            actor="user",
            action="score.calc",
            entity_type="score",
            entity_id=result["score_id"],
            input_snapshot=body,
            output_snapshot=result,
            ruleset_version=result.get("ruleset_version"),
            data_version=result.get("data_version"),
        )

        return api_ok(result)
    finally:
        conn.close()


@app.get("/api/v1/scores")
def scores_list(symbol: str, exchange: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        repo = ScoresRepo(conn)
        return api_ok(repo.list(symbol=str(symbol).zfill(6), exchange=str(exchange), limit=limit))
    finally:
        conn.close()


@app.post("/api/v1/plans/generate")
def plans_generate(body: dict):
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        svc = PlanService(conn)
        try:
            result = svc.generate_and_save(symbol=str(symbol).zfill(6), exchange=str(exchange))
        except ValueError as e:
            return api_err(ErrorCodes.DATA_NOT_READY, str(e), {"task": "ingest_bars_daily"}, status_code=409)

        AuditLogger(conn).log(
            actor="user",
            action="plan.generate",
            entity_type="plan",
            entity_id=result["plan_id"],
            input_snapshot=body,
            output_snapshot=result,
            data_version=result.get("based_on", {}),
        )

        return api_ok(result)
    finally:
        conn.close()


@app.post("/api/v1/plans")
def plans_create(body: dict):
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    plan = body.get("plan")
    based_on = body.get("based_on") or {}

    if not symbol or not exchange or not isinstance(plan, dict):
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol/exchange/plan are required")

    conn = connect(config.db_path)
    try:
        plan_id = PlansRepo(conn).create(symbol=str(symbol).zfill(6), exchange=str(exchange), plan_json=plan, based_on=based_on)
        AuditLogger(conn).log(
            actor="user",
            action="plan.create",
            entity_type="plan",
            entity_id=plan_id,
            input_snapshot=body,
            output_snapshot={"plan_id": plan_id},
        )
        return api_ok({"plan_id": plan_id})
    finally:
        conn.close()


@app.get("/api/v1/plans")
def plans_list(symbol: str, exchange: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        return api_ok(PlansRepo(conn).list(symbol=str(symbol).zfill(6), exchange=str(exchange), limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/plans/{plan_id}")
def plans_get(plan_id: str):
    conn = connect(config.db_path)
    try:
        plan = PlansRepo(conn).get(plan_id)
        if not plan:
            return api_err(ErrorCodes.VALIDATION_ERROR, "plan not found")
        return api_ok(plan)
    finally:
        conn.close()


@app.post("/api/v1/notes")
def notes_create(body: dict):
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    content_md = body.get("content_md")
    references = body.get("references")

    if not symbol or not exchange or not content_md:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol/exchange/content_md are required")

    conn = connect(config.db_path)
    try:
        note_id = NotesRepo(conn).create(
            symbol=str(symbol).zfill(6),
            exchange=str(exchange),
            content_md=str(content_md),
            references=references if isinstance(references, list) else None,
        )
        AuditLogger(conn).log(
            actor="user",
            action="note.create",
            entity_type="note",
            entity_id=note_id,
            input_snapshot=body,
            output_snapshot={"note_id": note_id},
        )
        return api_ok({"note_id": note_id})
    finally:
        conn.close()


@app.get("/api/v1/notes")
def notes_list(symbol: str, exchange: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        return api_ok(NotesRepo(conn).list(symbol=str(symbol).zfill(6), exchange=str(exchange), limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/notes/{note_id}")
def notes_get(note_id: str):
    conn = connect(config.db_path)
    try:
        note = NotesRepo(conn).get(note_id)
        if not note:
            return api_err(ErrorCodes.VALIDATION_ERROR, "note not found")
        return api_ok(note)
    finally:
        conn.close()


@app.get("/api/v1/watchlists")
def watchlist_get(list_type: str = "WATCH"):
    conn = connect(config.db_path)
    try:
        repo = WatchlistRepo(conn)
        return api_ok(repo.list_items(list_type=list_type))
    finally:
        conn.close()


@app.post("/api/v1/watchlists/items")
def watchlist_add_item(body: dict):
    list_type = body.get("list_type") or "WATCH"
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    tags = body.get("tags")

    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        repo = WatchlistRepo(conn)
        item_id = repo.add_item(list_type=list_type, symbol=str(symbol).zfill(6), exchange=str(exchange), tags=tags)
        AuditLogger(conn).log(
            actor="user",
            action="watchlist.add",
            entity_type="watchlist_item",
            entity_id=item_id,
            input_snapshot=body,
            output_snapshot={"item_id": item_id},
        )
        return api_ok({"item_id": item_id})
    finally:
        conn.close()


@app.delete("/api/v1/watchlists/items/{item_id}")
def watchlist_delete_item(item_id: str):
    conn = connect(config.db_path)
    try:
        repo = WatchlistRepo(conn)
        repo.delete_item(item_id)
        AuditLogger(conn).log(
            actor="user",
            action="watchlist.delete",
            entity_type="watchlist_item",
            entity_id=item_id,
            input_snapshot={"item_id": item_id},
            output_snapshot={"deleted": True},
        )
        return api_ok({"deleted": True})
    finally:
        conn.close()


@app.post("/api/v1/radar/templates")
def radar_create_template(body: dict):
    name = body.get("name")
    universe = body.get("universe") or {"type": "ALL"}
    rules = body.get("rules") or []

    if not name:
        return api_err(ErrorCodes.VALIDATION_ERROR, "name is required")

    conn = connect(config.db_path)
    try:
        repo = RadarRepo(conn)
        template_id = repo.create_template(name=str(name), universe=universe, rules=rules)
        return api_ok({"template_id": template_id})
    finally:
        conn.close()


@app.get("/api/v1/radar/templates")
def radar_list_templates():
    conn = connect(config.db_path)
    try:
        repo = RadarRepo(conn)
        return api_ok(repo.list_templates())
    finally:
        conn.close()


@app.post("/api/v1/radar/run")
def radar_run(body: dict):
    universe = body.get("universe") or {"type": "ALL"}
    rules = body.get("rules") or []

    task_id = task_manager.create_task("radar_run", {"universe": universe, "rules": rules})

    def _fn(conn, payload: dict) -> dict:
        svc = RadarService(conn)
        return svc.run(task_id=task_id, universe=payload.get("universe") or {}, rules=payload.get("rules") or [])

    task_manager.submit(task_id, _fn)
    return api_ok({"task_id": task_id})


@app.get("/api/v1/radar/results")
def radar_results(task_id: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        repo = RadarRepo(conn)
        return api_ok(repo.list_results(task_id=task_id, limit=limit))
    finally:
        conn.close()


@app.post("/api/v1/portfolios")
def portfolios_create(body: dict):
    name = body.get("name")
    initial_cash = float(body.get("initial_cash") or 1_000_000)
    if not name:
        return api_err(ErrorCodes.VALIDATION_ERROR, "name is required")

    conn = connect(config.db_path)
    try:
        repo = PortfolioRepo(conn)
        portfolio_id = repo.create(name=str(name), initial_cash=initial_cash)
        AuditLogger(conn).log(
            actor="user",
            action="portfolio.create",
            entity_type="portfolio",
            entity_id=portfolio_id,
            input_snapshot=body,
            output_snapshot={"portfolio_id": portfolio_id},
        )
        return api_ok({"portfolio_id": portfolio_id})
    finally:
        conn.close()


@app.get("/api/v1/portfolios")
def portfolios_list():
    conn = connect(config.db_path)
    try:
        repo = PortfolioRepo(conn)
        return api_ok(repo.list())
    finally:
        conn.close()


@app.get("/api/v1/portfolios/{portfolio_id}")
def portfolios_get(portfolio_id: str):
    conn = connect(config.db_path)
    try:
        repo = PortfolioRepo(conn)
        data = repo.get(portfolio_id)
        if not data:
            return api_err(ErrorCodes.VALIDATION_ERROR, "portfolio not found")
        return api_ok(data)
    finally:
        conn.close()


@app.post("/api/v1/rebalance/suggest")
def rebalance_suggest(body: dict):
    portfolio_id = body.get("portfolio_id")
    targets = body.get("targets") or []
    cash_reserve_ratio = float(body.get("cash_reserve_ratio") or 0.05)
    create_drafts = bool(body.get("create_drafts") or False)

    if not portfolio_id:
        return api_err(ErrorCodes.VALIDATION_ERROR, "portfolio_id is required")

    conn = connect(config.db_path)
    try:
        svc = RebalanceService(conn)
        result = svc.suggest(portfolio_id=str(portfolio_id), targets=targets, cash_reserve_ratio=cash_reserve_ratio)

        draft_ids: list[str] = []
        if create_drafts:
            repo = OrderDraftRepo(conn)
            for o in result.get("orders") or []:
                did = repo.create(
                    portfolio_id=str(portfolio_id),
                    symbol=o["symbol"],
                    exchange=o["exchange"],
                    side=o["side"],
                    order_type="LIMIT",
                    price=float(o.get("price")) if o.get("price") is not None else None,
                    qty=int(o["qty"]),
                    notes="rebalance",
                    origin="rebalance",
                )
                draft_ids.append(did)
            result["draft_ids"] = draft_ids

        AuditLogger(conn).log(
            actor="user",
            action="rebalance.suggest",
            entity_type="portfolio",
            entity_id=str(portfolio_id),
            input_snapshot=body,
            output_snapshot=result,
        )

        return api_ok(result)
    except ValueError as e:
        return api_err(ErrorCodes.VALIDATION_ERROR, str(e))
    finally:
        conn.close()


@app.post("/api/v1/order_drafts")
def order_drafts_create(body: dict):
    portfolio_id = body.get("portfolio_id")
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    side = body.get("side")
    order_type = body.get("order_type") or "LIMIT"
    price = body.get("price")
    qty = body.get("qty")
    notes = body.get("notes")
    origin = body.get("origin") or "manual"

    if not portfolio_id or not symbol or not exchange or not side or qty is None:
        return api_err(ErrorCodes.VALIDATION_ERROR, "portfolio_id/symbol/exchange/side/qty are required")

    conn = connect(config.db_path)
    try:
        repo = OrderDraftRepo(conn)
        draft_id = repo.create(
            portfolio_id=str(portfolio_id),
            symbol=str(symbol).zfill(6),
            exchange=str(exchange),
            side=str(side),
            order_type=str(order_type),
            price=float(price) if price is not None else None,
            qty=int(qty),
            notes=str(notes) if notes is not None else None,
            origin=str(origin),
        )
        AuditLogger(conn).log(
            actor="user",
            action="order_draft.create",
            entity_type="order_draft",
            entity_id=draft_id,
            input_snapshot=body,
            output_snapshot={"draft_id": draft_id},
        )
        return api_ok({"draft_id": draft_id})
    finally:
        conn.close()


@app.get("/api/v1/order_drafts")
def order_drafts_list(portfolio_id: str):
    conn = connect(config.db_path)
    try:
        repo = OrderDraftRepo(conn)
        return api_ok(repo.list(portfolio_id=str(portfolio_id)))
    finally:
        conn.close()


@app.patch("/api/v1/order_drafts/{draft_id}")
def order_drafts_patch(draft_id: str, body: dict):
    conn = connect(config.db_path)
    try:
        repo = OrderDraftRepo(conn)
        repo.update(draft_id, body)
        AuditLogger(conn).log(
            actor="user",
            action="order_draft.update",
            entity_type="order_draft",
            entity_id=draft_id,
            input_snapshot=body,
            output_snapshot={"updated": True},
        )
        return api_ok({"updated": True})
    finally:
        conn.close()


@app.delete("/api/v1/order_drafts/{draft_id}")
def order_drafts_delete(draft_id: str):
    conn = connect(config.db_path)
    try:
        repo = OrderDraftRepo(conn)
        repo.delete(draft_id)
        AuditLogger(conn).log(
            actor="user",
            action="order_draft.delete",
            entity_type="order_draft",
            entity_id=draft_id,
            input_snapshot={"draft_id": draft_id},
            output_snapshot={"deleted": True},
        )
        return api_ok({"deleted": True})
    finally:
        conn.close()


@app.post("/api/v1/risk/check")
def risk_check(body: dict):
    draft_ids = body.get("draft_ids") or []
    conn = connect(config.db_path)
    try:
        drafts = OrderDraftRepo(conn).get_many(list(draft_ids))
        if not drafts:
            return api_err(ErrorCodes.VALIDATION_ERROR, "no drafts found")
        riskcheck_id, result = RiskService(conn).check(draft_rows=drafts)
        AuditLogger(conn).log(
            actor="user",
            action="risk.check",
            entity_type="risk_check",
            entity_id=riskcheck_id,
            input_snapshot=body,
            output_snapshot=result,
            ruleset_version=result.get("ruleset_version"),
        )
        return api_ok({"riskcheck_id": riskcheck_id, **result})
    finally:
        conn.close()


@app.post("/api/v1/sim/confirm")
def sim_confirm(body: dict):
    draft_ids = body.get("draft_ids") or []
    riskcheck_id = body.get("riskcheck_id")
    if not riskcheck_id:
        return api_err(ErrorCodes.VALIDATION_ERROR, "riskcheck_id is required")

    conn = connect(config.db_path)
    try:
        drafts = OrderDraftRepo(conn).get_many(list(draft_ids))
        if not drafts:
            return api_err(ErrorCodes.VALIDATION_ERROR, "no drafts found")
        portfolio_id = drafts[0]["portfolio_id"]
        if any(d["portfolio_id"] != portfolio_id for d in drafts):
            return api_err(ErrorCodes.VALIDATION_ERROR, "drafts must belong to the same portfolio")
        result = SimService(conn).confirm(portfolio_id=portfolio_id, draft_rows=drafts, riskcheck_id=str(riskcheck_id))
        AuditLogger(conn).log(
            actor="user",
            action="sim.confirm",
            entity_type="sim_order",
            entity_id=result["order_id"],
            input_snapshot=body,
            output_snapshot=result,
        )
        return api_ok(result)
    except ValueError as e:
        return api_err(ErrorCodes.RISK_CHECK_FAIL, str(e), status_code=409)
    finally:
        conn.close()


@app.get("/api/v1/sim/orders")
def sim_orders(portfolio_id: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        repo = LedgerRepo(conn)
        return api_ok(repo.list_orders(portfolio_id=str(portfolio_id), limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/sim/trades")
def sim_trades(portfolio_id: str, limit: int = 500):
    conn = connect(config.db_path)
    try:
        repo = LedgerRepo(conn)
        return api_ok(repo.list_trades(portfolio_id=str(portfolio_id), limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/audit")
def audit_list(entity_type: str, entity_id: str, limit: int = 200):
    conn = connect(config.db_path)
    try:
        repo = AuditQueryRepo(conn)
        return api_ok(repo.list(entity_type=entity_type, entity_id=entity_id, limit=limit))
    finally:
        conn.close()


@app.post("/api/v1/tasks/run")
def run_task(body: dict):
    type_ = body.get("type")
    payload = body.get("payload") or {}
    if not type_:
        return api_err(ErrorCodes.VALIDATION_ERROR, "type is required")

    task_id = task_manager.create_task(type_, payload)

    if type_ == "ingest_instruments":
        def _fn(conn, _payload: dict) -> dict:
            repo = InstrumentsRepo(conn)
            for p in providers:
                st = p.status()
                if st.ok:
                    ingested = repo.upsert_many(p.iter_instruments())
                    return {"provider": p.name, "ingested": ingested}
            raise RuntimeError("no provider available")

        task_manager.submit(task_id, _fn)

    elif type_ == "ingest_bars_daily":
        def _fn(conn, _payload: dict) -> dict:
            symbols = _payload.get("symbols") or []
            start_date = _payload.get("start_date")
            end_date = _payload.get("end_date")
            adj = _payload.get("adj") or "RAW"

            repo = BarsRepo(conn)
            ingested_total = 0
            provider_used = None

            for item in symbols:
                sym = str(item.get("symbol") or "").zfill(6)
                exch = str(item.get("exchange") or "")
                if not sym or not exch:
                    continue

                last_err = None
                for p in providers:
                    st = p.status()
                    if not st.ok:
                        continue
                    try:
                        bars = p.fetch_bars_daily(
                            symbol=sym,
                            exchange=exch,
                            start_date=start_date,
                            end_date=end_date,
                            adj=adj,
                        )
                        ingested_total += repo.upsert_many(bars)
                        provider_used = p.name
                        last_err = None
                        break
                    except Exception as e:  # noqa: BLE001
                        last_err = str(e)
                        continue

                if last_err and provider_used is None:
                    raise RuntimeError(f"failed to ingest {sym}.{exch}: {last_err}")

            return {"provider": provider_used, "ingested": ingested_total}

        task_manager.submit(task_id, _fn)

    elif type_ == "ingest_fundamentals_daily":
        def _fn(conn, _payload: dict) -> dict:
            symbols = _payload.get("symbols") or []
            svc = FundamentalsIngestService(conn, tushare_token=config.tushare_token)
            return svc.ingest_daily_basic(symbols=symbols)

        task_manager.submit(task_id, _fn)

    elif type_ == "ingest_capital_flow_daily":
        def _fn(conn, _payload: dict) -> dict:
            symbols = _payload.get("symbols") or []
            svc = CapitalFlowIngestService(conn, tushare_token=config.tushare_token)
            return svc.ingest_moneyflow(symbols=symbols)

        task_manager.submit(task_id, _fn)

    else:
        task_manager.submit(task_id, lambda _conn, _p: {"status": "noop", "type": type_})

    return api_ok({"task_id": task_id})


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        return api_err(ErrorCodes.VALIDATION_ERROR, "task not found")
    return api_ok(task)


@app.get("/api/v1/tasks")
def list_tasks(limit: int = 50):
    return api_ok(task_manager.list_tasks(limit=limit))


# News API Endpoints
@app.get("/api/v1/news")
def news_list(symbol: str | None = None, exchange: str | None = None, limit: int = 100):
    """Get news list, optionally filtered by symbol/exchange."""
    conn = connect(config.db_path)
    try:
        from workbench.services.news import NewsRepo

        news_repo = NewsRepo(conn)
        news = news_repo.list(symbol=symbol, exchange=exchange, limit=limit)

        # If no news found and symbol provided, create mock news
        if not news and symbol and exchange:
            news_repo.create_mock_news(symbol, exchange, count=10)
            news = news_repo.list(symbol=symbol, exchange=exchange, limit=limit)

        return api_ok(news)
    finally:
        conn.close()


@app.post("/api/v1/news/{news_id}/save")
def news_save(news_id: str, body: dict | None = None):
    """Bookmark/unbookmark a news item."""
    saved = body.get("saved", True) if body else True

    conn = connect(config.db_path)
    try:
        from workbench.services.news import NewsRepo

        news_repo = NewsRepo(conn)
        news_repo.save_news(news_id, saved)

        return api_ok({"news_id": news_id, "saved": saved})
    finally:
        conn.close()


@app.post("/api/v1/news/ingest_mock")
def news_ingest_mock(body: dict):
    """Ingest mock news for a symbol (for testing/demo purposes)."""
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    count = body.get("count", 10)

    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.news import NewsRepo

        news_repo = NewsRepo(conn)
        news_repo.create_mock_news(symbol, exchange, count=count)

        return api_ok({"symbol": symbol, "exchange": exchange, "count": count})
    finally:
        conn.close()


# Risk Rules API Endpoints
@app.get("/api/v1/risk/rules")
def risk_get_rules():
    """Get all risk rules configuration."""
    conn = connect(config.db_path)
    try:
        from workbench.services.risk_rules import RiskRulesRepo

        rules_repo = RiskRulesRepo(conn)
        rules = rules_repo.get_all_rules()

        return api_ok(rules)
    finally:
        conn.close()


@app.patch("/api/v1/risk/rules")
def risk_update_rule(body: dict):
    """Update a risk rule value."""
    rule_name = body.get("rule_name")
    value = body.get("value")

    if not rule_name or value is None:
        return api_err(ErrorCodes.VALIDATION_ERROR, "rule_name and value are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.risk_rules import RiskRulesRepo

        rules_repo = RiskRulesRepo(conn)

        # Type conversion based on rule name
        if rule_name in ["max_position_per_symbol", "max_position_per_sector", "max_position_single_stock",
                        "min_cash_ratio", "min_cash_reserve", "price_deviation_limit",
                        "max_price_change_pct", "max_daily_trading_value", "max_order_value",
                        "min_order_value"]:
            value = float(value)
        elif rule_name in ["max_orders_per_day", "max_order_frequency_seconds", "lot_size"]:
            value = int(value)
        elif rule_name in ["ban_trading_on_limit_up", "ban_trading_on_limit_down",
                          "stop_loss_check", "profit_target_check"]:
            value = bool(value)

        rules_repo.update_rule(rule_name, value)

        return api_ok({"rule_name": rule_name, "value": value})
    finally:
        conn.close()


@app.get("/api/v1/risk/stats")
def risk_get_stats(portfolio_id: str):
    """Get risk-related statistics for a portfolio."""
    conn = connect(config.db_path)
    try:
        from workbench.services.risk_rules import RiskRulesRepo

        rules_repo = RiskRulesRepo(conn)

        stats = {
            "orders_today": rules_repo.get_recent_trades_count(portfolio_id, hours=24),
            "orders_last_hour": rules_repo.get_recent_orders_count(portfolio_id, minutes=60),
        }

        return api_ok(stats)
    finally:
        conn.close()


# Reports API Endpoints
@app.post("/api/v1/reports/stock")
def reports_generate_stock(body: dict):
    """Generate a stock research report."""
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    report_type = body.get("report_type", "comprehensive")

    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.reports import ReportsService

        reports = ReportsService(conn)
        report = reports.generate_stock_report(symbol, exchange, report_type)

        return api_ok(report)
    finally:
        conn.close()


@app.post("/api/v1/reports/portfolio")
def reports_generate_portfolio(body: dict):
    """Generate a portfolio report."""
    portfolio_id = body.get("portfolio_id")
    report_type = body.get("report_type", "monthly")

    if not portfolio_id:
        return api_err(ErrorCodes.VALIDATION_ERROR, "portfolio_id is required")

    conn = connect(config.db_path)
    try:
        from workbench.services.reports import ReportsService

        reports = ReportsService(conn)
        report = reports.generate_portfolio_report(portfolio_id, report_type)

        return api_ok(report)
    finally:
        conn.close()


@app.post("/api/v1/reports/trades")
def reports_generate_trades(body: dict):
    """Generate a trading activity report."""
    portfolio_id = body.get("portfolio_id")
    start_date = body.get("start_date")
    end_date = body.get("end_date")

    if not portfolio_id:
        return api_err(ErrorCodes.VALIDATION_ERROR, "portfolio_id is required")

    conn = connect(config.db_path)
    try:
        from workbench.services.reports import ReportsService

        reports = ReportsService(conn)
        report = reports.generate_trade_report(portfolio_id, start_date, end_date)

        return api_ok(report)
    finally:
        conn.close()


# Monitor API Endpoints
@app.post("/api/v1/monitor/rules")
def monitor_create_rule(body: dict):
    """Create a new monitoring rule."""
    portfolio_id = body.get("portfolio_id")
    symbol = body.get("symbol")
    exchange = body.get("exchange", "SSE")
    rule_type = body.get("rule_type")
    threshold = body.get("threshold")
    condition = body.get("condition", "above")
    enabled = body.get("enabled", True)

    if not rule_type or threshold is None:
        return api_err(ErrorCodes.VALIDATION_ERROR, "rule_type and threshold are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        monitor = MonitorService(conn)
        rule_id = monitor.create_rule(
            portfolio_id=portfolio_id,
            symbol=symbol,
            exchange=exchange,
            rule_type=rule_type,
            threshold=float(threshold),
            condition=condition,
            enabled=enabled,
        )

        return api_ok({"rule_id": rule_id})
    finally:
        conn.close()


@app.get("/api/v1/monitor/rules")
def monitor_list_rules(portfolio_id: str | None = None, symbol: str | None = None, enabled_only: bool = False):
    """List monitoring rules."""
    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        monitor = MonitorService(conn)
        rules = monitor.list_rules(portfolio_id=portfolio_id, symbol=symbol, enabled_only=enabled_only)

        # Convert to dict
        rules_data = []
        for rule in rules:
            rules_data.append({
                "rule_id": rule.rule_id,
                "portfolio_id": rule.portfolio_id,
                "symbol": rule.symbol,
                "exchange": rule.exchange,
                "rule_type": rule.rule_type,
                "threshold": rule.threshold,
                "condition": rule.condition,
                "enabled": rule.enabled,
                "created_at": rule.created_at,
                "trigger_count": rule.trigger_count,
                "last_triggered": rule.last_triggered,
            })

        return api_ok(rules_data)
    finally:
        conn.close()


@app.patch("/api/v1/monitor/rules/{rule_id}")
def monitor_update_rule(rule_id: str, body: dict):
    """Update a monitoring rule."""
    threshold = body.get("threshold")
    condition = body.get("condition")
    enabled = body.get("enabled")

    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        monitor = MonitorService(conn)
        monitor.update_rule(
            rule_id,
            threshold=float(threshold) if threshold is not None else None,
            condition=condition,
            enabled=enabled,
        )

        return api_ok({"rule_id": rule_id})
    finally:
        conn.close()


@app.delete("/api/v1/monitor/rules/{rule_id}")
def monitor_delete_rule(rule_id: str):
    """Delete a monitoring rule."""
    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        monitor = MonitorService(conn)
        monitor.delete_rule(rule_id)

        return api_ok({"rule_id": rule_id})
    finally:
        conn.close()


@app.post("/api/v1/monitor/check")
def monitor_check_rules():
    """Manually trigger rule checks."""
    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        monitor = MonitorService(conn)
        alerts = monitor.check_rules()

        # Save alerts to database
        for alert in alerts:
            monitor.save_alert(alert)

        # Convert to dict
        alerts_data = []
        for alert in alerts:
            alerts_data.append({
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "triggered_at": alert.triggered_at,
                "message": alert.message,
                "severity": alert.severity,
                "data": alert.data,
            })

        return api_ok({"alerts": alerts_data, "count": len(alerts)})
    finally:
        conn.close()


@app.get("/api/v1/monitor/alerts")
def monitor_list_alerts(limit: int = 100, since_hours: int = 24):
    """List recent alerts."""
    conn = connect(config.db_path)
    try:
        from workbench.services.monitor import MonitorService

        since = (datetime.now() - timedelta(hours=since_hours)).isoformat(timespec="seconds")

        monitor = MonitorService(conn)
        alerts = monitor.list_alerts(limit=limit, since=since)

        # Convert to dict
        alerts_data = []
        for alert in alerts:
            alerts_data.append({
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "triggered_at": alert.triggered_at,
                "message": alert.message,
                "severity": alert.severity,
                "data": alert.data,
            })

        return api_ok(alerts_data)
    finally:
        conn.close()


# Backtest API Endpoints
@app.post("/api/v1/backtest/run")
def backtest_run(body: dict):
    """Run a backtest on historical data."""
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    initial_cash = body.get("initial_cash", 1000000)
    signal_type = body.get("signal_type", "score_threshold")
    signal_params = body.get("signal_params", {})

    if not symbol or not exchange or not start_date or not end_date:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol, exchange, start_date, and end_date are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.backtest import BacktestService

        backtest = BacktestService(conn)
        result = backtest.run_backtest(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            signal_type=signal_type,
            signal_params=signal_params,
        )

        return api_ok(result)
    finally:
        conn.close()


@app.post("/api/v1/backtest/compare")
def backtest_compare(body: dict):
    """Compare multiple strategies."""
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    strategies = body.get("strategies", [])

    if not symbol or not exchange or not start_date or not end_date or not strategies:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol, exchange, start_date, end_date, and strategies are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.backtest import BacktestService

        backtest = BacktestService(conn)
        result = backtest.compare_strategies(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            strategies=strategies,
        )

        return api_ok(result)
    finally:
        conn.close()


@app.get("/api/v1/backtest/metrics")
def backtest_get_metrics():
    """Get available backtest metrics and their descriptions."""
    metrics = {
        "total_return_pct": "Total return percentage",
        "annualized_return_pct": "Annualized return percentage",
        "annualized_volatility_pct": "Annualized volatility (risk)",
        "sharpe_ratio": "Sharpe ratio (risk-adjusted return)",
        "max_drawdown_pct": "Maximum drawdown percentage",
        "win_rate": "Percentage of winning days",
        "cagr_pct": "Compound annual growth rate",
    }
    return api_ok(metrics)


# Factor Engineering API Endpoints
@app.post("/api/v1/factors/calculate")
def factors_calculate(body: dict):
    """Calculate factors for a symbol over a date range."""
    symbol = body.get("symbol")
    exchange = body.get("exchange")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    factor_names = body.get("factor_names", [])

    if not symbol or not exchange or not start_date or not end_date:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol, exchange, start_date, and end_date are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.factors import FactorService

        factor_service = FactorService(conn)
        result = factor_service.calculate_factors(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            factor_names=factor_names
        )

        return api_ok(result)
    finally:
        conn.close()


@app.post("/api/v1/factors/standardize")
def factors_standardize(body: dict):
    """Standardize factor values."""
    factor_values = body.get("factor_values", [])
    method = body.get("method", "zscore")

    if not factor_values:
        return api_err(ErrorCodes.VALIDATION_ERROR, "factor_values is required")

    conn = connect(config.db_path)
    try:
        from workbench.services.factors import FactorService

        factor_service = FactorService(conn)
        standardized = factor_service.standardize_factors(factor_values, method)

        return api_ok({"standardized_values": standardized, "method": method})
    finally:
        conn.close()


@app.post("/api/v1/factors/neutralize")
def factors_neutralize(body: dict):
    """Neutralize factor values against market benchmark."""
    factor_values = body.get("factor_values", [])
    market_values = body.get("market_values", [])

    if not factor_values or not market_values:
        return api_err(ErrorCodes.VALIDATION_ERROR, "factor_values and market_values are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.factors import FactorService

        factor_service = FactorService(conn)
        neutralized = factor_service.neutralize_factors(factor_values, market_values)

        return api_ok({"neutralized_values": neutralized})
    finally:
        conn.close()


@app.post("/api/v1/factors/analyze")
def factors_analyze(body: dict):
    """Analyze factor effectiveness."""
    factor_name = body.get("factor_name")
    factor_values = body.get("factor_values", [])
    returns = body.get("returns", [])

    if not factor_name or not factor_values or not returns:
        return api_err(ErrorCodes.VALIDATION_ERROR, "factor_name, factor_values, and returns are required")

    conn = connect(config.db_path)
    try:
        from workbench.services.factors import FactorService

        factor_service = FactorService(conn)
        analysis = factor_service.analyze_factor(factor_name, factor_values, returns)

        return api_ok(analysis)
    finally:
        conn.close()


@app.get("/api/v1/factors/library")
def factors_get_library():
    """Get list of available factors."""
    factor_library = {
        "technical_factors": [
            {"name": "MA5", "description": "5-day moving average", "type": "trend"},
            {"name": "MA10", "description": "10-day moving average", "type": "trend"},
            {"name": "MA20", "description": "20-day moving average", "type": "trend"},
            {"name": "RSI", "description": "14-day RSI", "type": "momentum"},
            {"name": "MACD", "description": "MACD indicator", "type": "momentum"},
            {"name": "BB", "description": "Bollinger Bands", "type": "volatility"},
            {"name": "VOL_MA", "description": "20-day average volume", "type": "volume"},
            {"name": "MOM_5", "description": "5-day price momentum", "type": "momentum"},
            {"name": "MOM_20", "description": "20-day price momentum", "type": "momentum"},
            {"name": "VOLATILITY", "description": "20-day volatility", "type": "volatility"},
            {"name": "VPT", "description": "Volume Price Trend", "type": "volume"},
        ],
        "fundamental_factors": [
            {"name": "PE", "description": "Price-to-Earnings ratio", "category": "valuation"},
            {"name": "PB", "description": "Price-to-Book ratio", "category": "valuation"},
            {"name": "PS", "description": "Price-to-Sales ratio", "category": "valuation"},
            {"name": "PCF", "description": "Price-to-Cash-Flow ratio", "category": "valuation"},
            {"name": "ROE", "description": "Return on Equity", "category": "profitability"},
            {"name": "ROA", "description": "Return on Assets", "category": "profitability"},
            {"name": "ROIC", "description": "Return on Invested Capital", "category": "profitability"},
            {"name": "REVENUE_GROWTH", "description": "Revenue growth rate", "category": "growth"},
            {"name": "PROFIT_GROWTH", "description": "Net profit growth rate", "category": "growth"},
            {"name": "DEBT_RATIO", "description": "Debt-to-Assets ratio", "category": "financial_health"},
            {"name": "CURRENT_RATIO", "description": "Current ratio", "category": "financial_health"},
        ],
        "processing_methods": [
            {"name": "zscore", "description": "Z-score standardization"},
            {"name": "rank", "description": "Rank normalization"},
            {"name": "winsorize", "description": "Winsorization (5%-95%)"},
        ],
    }
    return api_ok(factor_library)



@app.get("/api/v1/live/info")
def live_info():
    """Get current live trading provider configuration (P1)."""
    from workbench.services.live_trading import load_live_trading_config

    cfg = load_live_trading_config()
    return api_ok(cfg.__dict__)


@app.post("/api/v1/live/ping")
def live_ping():
    """Ping the live trading provider (best-effort)."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.ping())
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.get("/api/v1/live/accounts")
def live_accounts():
    """List live trading accounts (or portfolios in sim mode)."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.list_accounts())
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.get("/api/v1/live/positions")
def live_positions():
    """List positions (live or simulated)."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.list_positions())
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.get("/api/v1/live/orders")
def live_orders(active_only: bool = False, limit: int = 200):
    """List orders from the live provider."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.list_orders(active_only=active_only, limit=limit))
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.get("/api/v1/live/trades")
def live_trades(limit: int = 500):
    """List trades from the live provider."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.list_trades(limit=limit))
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.post("/api/v1/live/orders")
def live_send_order(body: dict):
    """Send an order to the live provider (or create a draft in sim mode)."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.send_order(body))
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.post("/api/v1/live/orders/cancel")
def live_cancel_order(body: dict):
    """Cancel an order on the live provider (best-effort)."""
    from workbench.services.live_trading import LiveTradingNotAvailable, get_adapter

    conn = connect(config.db_path)
    try:
        try:
            adapter = get_adapter(conn=conn)
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
        try:
            return api_ok(adapter.cancel_order(body))
        except LiveTradingNotAvailable as e:
            return api_err("LIVE_NOT_AVAILABLE", str(e), status_code=409)
    finally:
        conn.close()


@app.post("/api/v1/assistant/chat")
def assistant_chat(body: dict):
    """Offline-first assistant (P1): produces conclusion/evidence/risks/plan + citations."""
    from workbench.services.assistant import AssistantRequest, AssistantService

    prompt = body.get("prompt") or body.get("text") or ""
    req = AssistantRequest(
        mode=str(body.get("mode") or "qa"),
        prompt=str(prompt),
        target=body.get("target"),
        style=str(body.get("style") or "balanced"),
        cite=str(body.get("cite") or "news"),
        save_note=bool(body.get("save_note") or False),
    )

    conn = connect(config.db_path)
    try:
        svc = AssistantService(conn)
        try:
            return api_ok(svc.chat(req))
        except ValueError as e:
            return api_err(ErrorCodes.VALIDATION_ERROR, str(e))
    finally:
        conn.close()


@app.post("/api/v1/kb/documents")
def kb_create(body: dict):
    """Create a knowledge base document (P1)."""
    from workbench.services.knowledge_base import KnowledgeBaseRepo

    doc_type = str(body.get("doc_type") or "note")
    title = body.get("title")
    content = body.get("content")

    conn = connect(config.db_path)
    try:
        repo = KnowledgeBaseRepo(conn)
        try:
            doc = repo.create(
                doc_type=doc_type,
                title=str(title) if title is not None else None,
                content=str(content or ""),
                source_url=str(body.get("source_url")) if body.get("source_url") else None,
                symbol=str(body.get("symbol")) if body.get("symbol") else None,
                exchange=str(body.get("exchange")) if body.get("exchange") else None,
                tags=body.get("tags") if isinstance(body.get("tags"), list) else None,
            )
            return api_ok(doc)
        except ValueError as e:
            return api_err(ErrorCodes.VALIDATION_ERROR, str(e))
    finally:
        conn.close()


@app.get("/api/v1/kb/documents")
def kb_list(symbol: str | None = None, exchange: str | None = None, limit: int = 100):
    """List knowledge base documents."""
    from workbench.services.knowledge_base import KnowledgeBaseRepo

    conn = connect(config.db_path)
    try:
        repo = KnowledgeBaseRepo(conn)
        return api_ok(repo.list(symbol=symbol, exchange=exchange, limit=limit))
    finally:
        conn.close()


@app.get("/api/v1/kb/search")
def kb_search(q: str, symbol: str | None = None, exchange: str | None = None, limit: int = 20):
    """Search the local knowledge base via SQLite FTS."""
    from workbench.services.knowledge_base import KnowledgeBaseRepo

    if not q:
        return api_err(ErrorCodes.VALIDATION_ERROR, "q is required")

    conn = connect(config.db_path)
    try:
        repo = KnowledgeBaseRepo(conn)
        return api_ok(repo.search(q=q, symbol=symbol, exchange=exchange, limit=limit))
    finally:
        conn.close()


@app.post("/api/v1/kb/ingest/news")
def kb_ingest_news(body: dict):
    """Ingest existing news_items into the knowledge base for offline search."""
    from workbench.services.knowledge_base import KnowledgeBaseRepo
    from workbench.services.news import NewsRepo

    symbol = str(body.get("symbol") or "")
    exchange = str(body.get("exchange") or "")
    limit = int(body.get("limit") or 200)
    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        news = NewsRepo(conn).list(symbol=symbol, exchange=exchange, limit=limit)
        kb = KnowledgeBaseRepo(conn)
        n = 0
        for item in news:
            title = item.get("title")
            content = "\n\n".join([x for x in [item.get("summary"), item.get("url")] if x])
            kb.create(
                doc_type="news",
                title=str(title) if title else None,
                content=content or (title or ""),
                source_url=item.get("url"),
                symbol=symbol,
                exchange=exchange,
                tags=item.get("keywords") if isinstance(item.get("keywords"), list) else None,
            )
            n += 1
        return api_ok({"ingested": n})
    finally:
        conn.close()


@app.post("/api/v1/kb/ingest/notes")
def kb_ingest_notes(body: dict):
    """Ingest existing notes into the knowledge base for offline search."""
    from workbench.services.knowledge_base import KnowledgeBaseRepo
    from workbench.services.notes import NotesRepo

    symbol = str(body.get("symbol") or "")
    exchange = str(body.get("exchange") or "")
    limit = int(body.get("limit") or 200)
    if not symbol or not exchange:
        return api_err(ErrorCodes.VALIDATION_ERROR, "symbol and exchange are required")

    conn = connect(config.db_path)
    try:
        notes = NotesRepo(conn).list(symbol=symbol, exchange=exchange, limit=limit)
        kb = KnowledgeBaseRepo(conn)
        n = 0
        for note in notes:
            kb.create(
                doc_type="note",
                title=f"note {note.get('note_id')}" if note.get("note_id") else None,
                content=str(note.get("content") or ""),
                source_url=None,
                symbol=symbol,
                exchange=exchange,
                tags=None,
            )
            n += 1
        return api_ok({"ingested": n})
    finally:
        conn.close()
