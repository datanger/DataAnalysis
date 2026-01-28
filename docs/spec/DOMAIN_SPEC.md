# 领域模型规范（Domain Spec）

- 版本：v0.1
- 日期：2026-01-24
- 目标：统一 4 个子项目（`StockAnal_Sys`/`vnpy`/`FinRL`/`DeepResearch`）在“标的、数据、组合、交易、审计”上的字段口径，避免后续集成返工。

## 1. 命名与标识

### 1.1 市场与交易所
- `exchange`（枚举）：`SSE`（上交所）、`SZSE`（深交所）
- `market`（枚举）：`CN_A`（A股）

### 1.2 标的标识
- `symbol`：不含后缀的代码字符串，例如 `600519`、`000001`
- `ts_code`：带后缀代码（TuShare口径），例如 `600519.SH`、`000001.SZ`
- `vt_symbol`：vnpy口径，`{symbol}.{exchange}`，例如 `600519.SSE`
- 统一规则：系统内部主键使用 `(symbol, exchange)`；对外展示可使用 `ts_code`。

### 1.3 时间口径
- `trade_date`：交易日，`YYYY-MM-DD`（字符串）
- `ts`：时间戳（UTC+8，ISO8601字符串或毫秒整数，二选一但全局一致）
- 统一规则：
  - 日频数据用 `trade_date`
  - 盘中/撮合/订单事件用 `ts`

### 1.4 货币与单位
- `currency`：`CNY`
- 金额：以“元”为单位（浮点或Decimal）；数量：以“股/份”为单位（整数）
- 比例：使用 `0~1`（如 `0.15` 表示 15%），UI显示时格式化为百分比。

## 2. 行情（Market Data）

### 2.1 日K（BarDaily）
字段：
- 主键：`(symbol, exchange, trade_date, adj)`
- `adj`（枚举）：`RAW`（不复权）、`QFQ`（前复权）、`HFQ`（后复权）
- `open/high/low/close`：float
- `volume`：float（股/份）
- `amount`：float（元）
- `pre_close`：float（用于涨跌停判断与收益计算，若不可得则为空）
- `source`：provider名（如 `akshare`/`tushare`）
- `quality`（枚举）：`OK`/`MISSING`/`DELAYED`/`SUSPECT`
- `ingested_at`：入库时间戳

### 2.2 指标（IndicatorDaily）
- 主键：`(symbol, exchange, trade_date, adj, indicator_name, indicator_params_hash)`
- `indicator_name`：如 `MA`/`RSI`/`MACD`/`BOLL`
- `params_json`：参数JSON（用于复现）
- `value_json`：结果JSON（单值或多值，如MACD三元）

## 3. 基本面与估值（Fundamental）

### 3.1 财务快照（FundamentalSnapshot）
- 主键：`(symbol, exchange, report_period, report_type)`
- `report_period`：`YYYYQn` 或 `YYYY-MM-DD`（按数据源能力）
- `report_type`：`Q`/`A`
- 最小字段集合（V1）：`revenue`, `net_profit`, `roe`, `gross_margin`, `debt_ratio`
- 估值最小字段集合（V1）：`pe_ttm`, `pb`, `ps_ttm`, `mv`（市值）
- `source/quality/ingested_at`

## 4. 资金流（Capital Flow）

### 4.1 资金流快照（CapitalFlowDaily）
- 主键：`(symbol, exchange, trade_date)`
- 字段（按可得性）：`net_inflow`, `main_inflow`, `northbound_net` 等
- `source/quality/ingested_at`

## 5. 资讯（News/Event）

### 5.1 新闻条目（NewsItem）
- 主键：`news_id`（uuid）
- 关联：`symbol, exchange`（可空：宏观/行业新闻）
- `published_at`、`title`、`summary`、`source_site`、`url`、`keywords_json`
- `saved`（bool）：用户收藏
- `quality`：是否抓取失败/摘要缺失

## 6. 评分、信号与计划（Decision Artifacts）

### 6.1 评分（ScoreSnapshot）
- 主键：`score_id`（uuid）
- `symbol/exchange/trade_date`
- `score_total`（0~100）
- `breakdown_json`：分项得分（技术/基本面/资金/事件）
- `reasons_json`：命中原因列表（可展示给用户）
- `ruleset_version`：评分规则版本
- `data_version`：关键输入数据版本（最后更新时间/任务id集合）

### 6.2 操作计划（TradePlan）
- 主键：`plan_id`（uuid）
- `symbol/exchange/created_at`
- `plan_version`：递增
- `plan_json`：结构化字段（见下）
- `based_on`：引用（score_id、news_id列表、indicator_params_hash等）

TradePlan.plan_json（V1最小集合）：
- `direction`：`LONG`（V1只做多）
- `entry`：入场（区间/条件）
- `exit_take_profit`：止盈规则
- `exit_stop_loss`：止损规则
- `position_sizing`：建议仓位（0~1）
- `risk_notes`：风险点列表
- `assumptions`：关键假设

## 7. 组合与交易（Portfolio & Trading）

### 7.1 组合（Portfolio）
- 主键：`portfolio_id`（uuid）
- `name`、`base_currency=CNY`

### 7.2 持仓（Position）
- 主键：`(portfolio_id, symbol, exchange)`
- `qty`、`avg_cost`、`market_value`、`unrealized_pnl`

### 7.3 订单草稿（OrderDraft）
- 主键：`draft_id`（uuid）
- `portfolio_id`、`symbol/exchange`
- `side`：`BUY`/`SELL`
- `order_type`：`LIMIT`（V1默认）
- `price`（可空：若用市价模拟）
- `qty`
- `notes`（用户备注）
- `origin`：来源（`rebalance`/`plan`/`manual`）

### 7.4 风控校验结果（RiskCheckResult）
- 主键：`riskcheck_id`（uuid）
- `draft_id`
- `status`：`PASS`/`WARN`/`FAIL`
- `items_json`：[{code, level, message, suggestion}]
- `ruleset_version`

### 7.5 模拟订单/成交（SimOrder/SimTrade）
- `order_id`、`status`、`submitted_at`、`filled_qty`、`avg_fill_price`
- `trade_id`、`filled_at`、`fill_price`、`fill_qty`、`fee`、`slippage`

## 8. 审计与可追溯（Audit）
- 任一“评分/计划/调仓/确认/成交”必须写入：
  - `actor`（用户/系统）、`action`、`ts`
  - `input_snapshot_json`、`output_snapshot_json`
  - `ruleset_version`、`data_version`、`model_version`（V1可空）

