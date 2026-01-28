# API 规范（v0.1）

- 目标：为 Web 前端提供稳定、可版本化、可观测的接口；页面不直连数据源。
- 通用约定：
  - Base path：`/api/v1`
  - 响应统一结构：`{ ok: bool, data: any, error?: { code, message, details? } }`
  - 时间：日频用 `trade_date`；事件用 `ts`

## 1. 健康检查
- `GET /api/v1/health`

## 2. 标的与列表
- `GET /api/v1/instruments/search?q=`
- `GET /api/v1/watchlists?list_type=WATCH|BLACKLIST|...`
- `POST /api/v1/watchlists/items`（body: { list_type, symbol, exchange, tags? }）
- `DELETE /api/v1/watchlists/items/{item_id}`

## 3. 数据更新任务
- `POST /api/v1/tasks/run`（body: { type, payload }）
  - `type=ingest_instruments`
  - `type=ingest_bars_daily`（payload: { symbols:[{symbol,exchange}], start_date?, end_date?, adj? })
  - `type=ingest_fundamentals_daily`（payload: { symbols:[{symbol,exchange}] }；需配置 `TUSHARE_TOKEN`）
  - `type=ingest_capital_flow_daily`（payload: { symbols:[{symbol,exchange}] }；需配置 `TUSHARE_TOKEN`）
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks`

## 4. 选股雷达
- `POST /api/v1/radar/templates`
- `GET /api/v1/radar/templates`
- `POST /api/v1/radar/run`
- `GET /api/v1/radar/results?task_id=&limit=`

## 5. 个股工作台
- `GET /api/v1/stocks/{exchange}/{symbol}/workspace?adj=`

## 6. 评分
- `POST /api/v1/scores/calc`
- `GET /api/v1/scores?symbol=&exchange=&limit=`

## 7. 操作计划（Trade Plan）
- `POST /api/v1/plans/generate`
- `POST /api/v1/plans`
- `GET /api/v1/plans?symbol=&exchange=&limit=`
- `GET /api/v1/plans/{plan_id}`

## 8. 研究纪要
- `POST /api/v1/notes`
- `GET /api/v1/notes?symbol=&exchange=&limit=`
- `GET /api/v1/notes/{note_id}`

## 9. 组合
- `POST /api/v1/portfolios`
- `GET /api/v1/portfolios`
- `GET /api/v1/portfolios/{portfolio_id}`

## 10. 调仓建议（V1：目标权重 -> 建议买卖清单）
- `POST /api/v1/rebalance/suggest`（body: { portfolio_id, targets:[{symbol,exchange,weight}], cash_reserve_ratio?, create_drafts? }）

## 11. 订单草稿
- `POST /api/v1/order_drafts`
- `GET /api/v1/order_drafts?portfolio_id=`
- `PATCH /api/v1/order_drafts/{draft_id}`
- `DELETE /api/v1/order_drafts/{draft_id}`

## 12. 风控与确认执行（模拟）
- `POST /api/v1/risk/check`
- `POST /api/v1/sim/confirm`

## 13. 台账
- `GET /api/v1/sim/orders?portfolio_id=&limit=`
- `GET /api/v1/sim/trades?portfolio_id=&limit=`

## 14. 审计
- `GET /api/v1/audit?entity_type=&entity_id=&limit=`

## 错误码建议（示例）
- `DATA_NOT_READY`：数据未更新/需跑任务
- `RISK_CHECK_FAIL`：风控拦截（409）
- `VALIDATION_ERROR`：参数校验失败
