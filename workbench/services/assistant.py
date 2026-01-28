from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssistantRequest:
    mode: str  # qa | research
    prompt: str
    target: str | None = None  # e.g. "600519" or "SSE/600519"
    style: str = "balanced"  # brief | balanced | deep
    cite: str = "news"  # news | both | kb
    save_note: bool = False


class AssistantService:
    """Offline-first assistant that stitches together local signals + sources.

    This is intentionally deterministic and works without network/LLM.
    If you later plug in DeepResearch/LLM, keep this as the fallback.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _parse_target(target: str | None) -> tuple[str | None, str | None]:
        if not target:
            return None, None
        t = str(target).strip()
        if not t:
            return None, None
        if "/" in t:
            a, b = t.split("/", 1)
            exch = a.strip().upper()
            sym = b.strip()
            if sym:
                return sym, exch or None
        # Heuristic: 6-digit A-share code => default SSE
        digits = "".join([c for c in t if c.isdigit()])
        if len(digits) >= 6:
            return digits[:6], "SSE"
        return None, None

    def chat(self, req: AssistantRequest) -> dict[str, Any]:
        from datetime import datetime

        from workbench.services.knowledge_base import KnowledgeBaseRepo
        from workbench.services.notes import NotesRepo
        from workbench.services.workspace import WorkspaceService

        if not req.prompt or not req.prompt.strip():
            raise ValueError("prompt is required")

        symbol, exchange = self._parse_target(req.target)

        ws: dict[str, Any] | None = None
        if symbol and exchange:
            ws = WorkspaceService(self._conn).get_workspace(symbol=symbol, exchange=exchange)

        # Build citations/sources.
        sources: list[dict[str, Any]] = []
        if ws and req.cite in ("news", "both"):
            for n in (ws.get("news") or [])[:6]:
                sources.append(
                    {
                        "type": "news",
                        "id": n.get("news_id"),
                        "title": n.get("title"),
                        "summary": n.get("summary"),
                        "source_site": n.get("source_site"),
                        "published_at": n.get("published_at"),
                        "url": n.get("url"),
                    }
                )

        kb = KnowledgeBaseRepo(self._conn)
        if req.cite in ("kb", "both"):
            q = req.prompt.strip()
            if symbol and exchange:
                hits = kb.search(q=q, symbol=symbol, exchange=exchange, limit=6)
            else:
                hits = kb.search(q=q, limit=6)
            for h in hits:
                sources.append(
                    {
                        "type": "kb",
                        "id": h.get("doc_id"),
                        "title": h.get("title"),
                        "snippet": h.get("snippet"),
                        "source_url": h.get("source_url"),
                        "created_at": h.get("created_at"),
                    }
                )

        # Produce a compact report-style answer.
        report = self._build_report(req=req, ws=ws, symbol=symbol, exchange=exchange, sources=sources)

        # Optionally persist to notes (audit trail).
        note_id = None
        if req.save_note and symbol and exchange:
            note_md = self._to_markdown(report, sources)
            note_id = NotesRepo(self._conn).create(
                symbol=symbol,
                exchange=exchange,
                content_md=note_md,
                references=sources,
            )

        return {
            "assistant_id": f"asst_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode": req.mode,
            "target": {"symbol": symbol, "exchange": exchange} if symbol and exchange else None,
            "prompt": req.prompt,
            "report": report,
            "sources": sources,
            "note_id": note_id,
        }

    def _build_report(
        self,
        *,
        req: AssistantRequest,
        ws: dict[str, Any] | None,
        symbol: str | None,
        exchange: str | None,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        score = None
        latest_score = (ws or {}).get("latest_score") if ws else None
        if latest_score and latest_score.get("score_total") is not None:
            try:
                score = float(latest_score.get("score_total"))
            except Exception:
                score = None

        direction = "NEUTRAL"
        confidence = "MED"
        if score is not None:
            if score >= 80:
                direction, confidence = "LONG", "HIGH"
            elif score >= 65:
                direction, confidence = "LEAN_LONG", "MED"
            elif score <= 40:
                direction, confidence = "AVOID", "HIGH"
            elif score <= 55:
                direction, confidence = "LEAN_SHORT", "MED"

        # Evidence bullets
        evidence: list[str] = []
        if ws and (ws.get("price_bars") or []):
            bars = ws["price_bars"]
            last = bars[-1]
            evidence.append(f"最新收盘: {last.get('close')} (RAW)")

        if ws and (ws.get("indicators") or []):
            # We only surface a couple of human-readable cues.
            for ind in ws["indicators"]:
                if ind.get("indicator_name") == "RSI":
                    rsi = (ind.get("value_json") or {}).get("rsi")
                    if rsi is not None:
                        evidence.append(f"RSI(14): {float(rsi):.1f}")
                if ind.get("indicator_name") == "MA":
                    ma5 = (ind.get("value_json") or {}).get("ma5")
                    ma20 = (ind.get("value_json") or {}).get("ma20")
                    if ma5 is not None and ma20 is not None:
                        evidence.append(f"均线: MA5 {float(ma5):.2f} / MA20 {float(ma20):.2f}")

        fundamentals = (ws or {}).get("fundamentals_summary") if ws else None
        if fundamentals:
            pe = fundamentals.get("pe_ttm")
            pb = fundamentals.get("pb")
            if pe is not None or pb is not None:
                evidence.append(f"估值: PE(TTM) {pe if pe is not None else '--'} / PB {pb if pb is not None else '--'}")

        cf = (ws or {}).get("capital_flow") if ws else None
        if cf and cf.get("net_inflow") is not None:
            try:
                evidence.append(f"资金: 净流入 {float(cf['net_inflow'])/10000:.2f}万")
            except Exception:
                pass

        if score is not None:
            evidence.append(f"综合评分: {score:.1f}/100")

        # Risks
        risks: list[str] = []
        if ws and not fundamentals:
            risks.append("基本面字段缺失，结论置信度下降（建议补数或切换数据源）")
        if ws and not cf:
            risks.append("资金流字段缺失，无法验证主力承接/异动")
        if ws and not (ws.get("news") or []):
            risks.append("新闻/公告为空，建议刷新数据或导入本地资料")
        if score is not None and score >= 80:
            risks.append("高分阶段容易出现拥挤交易与回撤，需设置触发价与止损")
        if score is not None and score <= 55:
            risks.append("弱势阶段容易反复，避免追涨；等待结构确认")

        # Action plan
        plan: list[str] = []
        if symbol and exchange:
            plan.append("先看：消息面/资金是否与技术结论一致（不一致则降低仓位）")
            plan.append("设定：观察价/触发条件/止损止盈（写入操作计划并版本化）")
            plan.append("执行：先生成订单草稿 → 风控校验 → 用户确认")
        else:
            plan.append("建议绑定对象（股票代码）以获得更完整的可追溯证据链")

        # Output formatting density.
        if req.style == "brief":
            evidence = evidence[:4]
            risks = risks[:3]
            plan = plan[:3]
        elif req.style == "deep":
            # keep as-is (still compact)
            pass
        else:
            evidence = evidence[:6]
            risks = risks[:4]
            plan = plan[:4]

        conclusion = (
            f"{symbol}.{exchange} {direction}（置信度 {confidence}）"
            if symbol and exchange
            else f"{direction}（置信度 {confidence}）"
        )

        return {
            "conclusion": conclusion,
            "evidence": evidence,
            "risks": risks,
            "plan": plan,
            "score": score,
        }

    @staticmethod
    def _to_markdown(report: dict[str, Any], sources: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        lines.append(f"## 结论\n{report.get('conclusion') or '--'}\n")
        lines.append("## 依据")
        for e in report.get("evidence") or []:
            lines.append(f"- {e}")
        lines.append("")
        lines.append("## 风险")
        for r in report.get("risks") or []:
            lines.append(f"- {r}")
        lines.append("")
        lines.append("## 计划")
        for p in report.get("plan") or []:
            lines.append(f"- {p}")
        lines.append("")
        if sources:
            lines.append("## 引用")
            for s in sources[:10]:
                if s.get("type") == "news":
                    title = s.get("title") or "news"
                    url = s.get("url") or ""
                    src = s.get("source_site") or ""
                    lines.append(f"- [NEWS] {title} {src} {url}".strip())
                else:
                    title = s.get("title") or "kb"
                    url = s.get("source_url") or ""
                    lines.append(f"- [KB] {title} {url}".strip())
            lines.append("")
        return "\n".join(lines)
