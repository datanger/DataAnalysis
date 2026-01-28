# -*- coding: utf-8 -*-
"""
Minimal UI preview server.

This repo's full web_server.py pulls in many analysis/data dependencies. During UI iteration
we want to be able to boot the UI even if those optional deps are not installed yet.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for


_BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(_BASE_DIR / "templates"),
    static_folder=str(_BASE_DIR / "static"),
    static_url_path="/static",
)

_wb_api = (os.getenv("WORKBENCH_API_BASE") or "").strip()
if not _wb_api:
    _wb_host = (os.getenv("WORKBENCH_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    _wb_port = (os.getenv("WORKBENCH_PORT") or "8000").strip() or "8000"
    _wb_api = f"http://{_wb_host}:{_wb_port}/api/v1"
app.config["WORKBENCH_API_BASE"] = _wb_api


def _render(name: str):
    # Keep errors simple and visible in the UI preview stage.
    return render_template(name)


@app.get("/")
def index():
    return _render("index.html")


@app.get("/news")
def news():
    return _render("news.html")


# Main stock-selection workspace (UI-first).
@app.get("/workbench")
def workbench():
    return _render("workbench.html")


@app.get("/research")
def research():
    return _render("research.html")


# Page stubs: allow navigation to exist while backend features are pending.
@app.get("/dashboard")
def dashboard():
    return _render("dashboard.html")


@app.get("/fundamental")
def fundamental():
    return _render("fundamental.html")


@app.get("/capital_flow")
def capital_flow():
    return _render("capital_flow.html")


@app.get("/market_scan")
def market_scan():
    # Direct replacement: market_scan entry is now the unified workbench.
    return redirect(url_for("workbench"))


@app.get("/scenario_predict")
def scenario_predict():
    return _render("scenario_predict.html")


@app.get("/portfolio")
def portfolio():
    return _render("portfolio.html")


@app.get("/qa")
def qa():
    return redirect(url_for("research"))


@app.get("/risk_monitor")
def risk_monitor():
    return _render("risk_monitor.html")


@app.get("/industry_analysis")
def industry_analysis():
    return _render("industry_analysis.html")


@app.get("/agent_analysis")
def agent_analysis():
    return redirect(url_for("research"))


@app.get("/etf_analysis")
def etf_analysis():
    return _render("etf_analysis.html")


@app.get("/stock_detail/<stock_code>")
def stock_detail(stock_code: str):
    # Some templates expect this route to exist; we don't compute anything yet.
    return _render("stock_detail.html")


# --- Minimal APIs used by layout.js / global task monitor ---
@app.get("/api/active_tasks")
def api_active_tasks():
    return jsonify({"active_tasks": []})


@app.post("/api/delete_agent_analysis")
def api_delete_agent_analysis():
    body = request.get_json(silent=True) or {}
    _ = body.get("task_ids", [])
    return jsonify({"success": True, "message": "UI preview: no tasks to delete"})


# --- Workbench scan APIs (UI preview stubs) ---
_SCAN_TASKS: dict[str, dict] = {}


def _mock_scan_result(min_score: int = 60):
    rows = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "industry": "白酒",
            "score": 92,
            "price": 1688.8,
            "change_pct": 1.23,
            "suggestion": "强势观察",
        },
        {
            "code": "300750",
            "name": "宁德时代",
            "industry": "锂电",
            "score": 83,
            "price": 158.6,
            "change_pct": 2.81,
            "suggestion": "反弹跟踪",
        },
        {
            "code": "688981",
            "name": "中芯国际",
            "industry": "半导体",
            "score": 81,
            "price": 43.2,
            "change_pct": 1.05,
            "suggestion": "主题驱动",
        },
        {
            "code": "000001",
            "name": "平安银行",
            "industry": "银行",
            "score": 78,
            "price": 12.34,
            "change_pct": -0.62,
            "suggestion": "低估修复",
        },
    ]
    return [r for r in rows if int(r.get("score") or 0) >= int(min_score)]


@app.post("/api/start_market_scan")
def api_start_market_scan():
    payload = request.get_json(silent=True) or {}
    min_score = int(payload.get("min_score") or 60)
    task_id = uuid4().hex[:12]
    _SCAN_TASKS[task_id] = {
        "status": "completed",
        "progress": 100,
        "result": _mock_scan_result(min_score=min_score),
    }
    return jsonify({"success": True, "task_id": task_id})


@app.get("/api/scan_status/<task_id>")
def api_scan_status(task_id: str):
    task = _SCAN_TASKS.get(task_id)
    if not task:
        return jsonify({"success": False, "status": "failed", "error": "unknown task"}), 404
    return jsonify({"success": True, **task})


@app.post("/api/cancel_scan/<task_id>")
def api_cancel_scan(task_id: str):
    task = _SCAN_TASKS.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "unknown task"}), 404
    task["status"] = "cancelled"
    return jsonify({"success": True, "task_id": task_id})


@app.get("/api/board_stocks")
def api_board_stocks():
    board = (request.args.get("board") or "").strip()
    # UI preview: best-effort demo list.
    mapping = {
        "kc50": ["688981", "688111", "688036"],
        "kc100": ["688981", "688012", "688041"],
        "bj50": ["430047", "832982", "830779"],
    }
    return jsonify({"success": True, "board": board, "stocks": mapping.get(board, [])})


# Optional convenience stubs (avoid 404 noise when opening other pages)
@app.get("/api/latest_news")
def api_latest_news():
    # Best-effort: if the project already has its news_fetcher deps available,
    # reuse it so UI preview can show real data; otherwise return empty.
    try:
        from app.analysis.news_fetcher import news_fetcher  # type: ignore
    except Exception:
        return jsonify({"success": True, "news": []})

    try:
        days = int(request.args.get("days", 1))
        limit = int(request.args.get("limit", 80))
        only_important = request.args.get("important", "0") == "1"
        news_type = request.args.get("type", "all")

        news_data = news_fetcher.get_latest_news(days=days, limit=limit)

        if only_important:
            important_keywords = ["重要", "利好", "重磅", "突发", "关注"]
            news_data = [
                n
                for n in news_data
                if any(k in (n.get("content", "") or "") for k in important_keywords)
            ]

        if news_type == "hotspot":
            hotspot_keywords = ["舆情", "热点", "热议", "热搜", "话题", "焦点", "重磅", "突发", "要闻"]

            def has_kw(item):
                title = item.get("title", "") or ""
                content = item.get("content", "") or ""
                return any(k in title for k in hotspot_keywords) or any(k in content for k in hotspot_keywords)

            news_data = [n for n in news_data if has_kw(n)]

        return jsonify({"success": True, "news": news_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post("/api/news/refresh")
def api_news_refresh():
    """Fetch and cache latest news (best-effort)."""
    try:
        from app.analysis.news_fetcher import news_fetcher  # type: ignore
    except Exception:
        return jsonify({"success": False, "error": "news_fetcher not available"}), 501

    try:
        ok = bool(news_fetcher.fetch_and_save())
        return jsonify({"success": True, "ok": ok})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
