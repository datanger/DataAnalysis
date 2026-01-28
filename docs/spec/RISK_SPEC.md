# 风控与确认下单规范（v0.1，模拟通道）

- 目标：订单执行必须经过风控校验；用户“确认”是最后一道闸。
- 适用：P0 模拟通道；P1 实盘通道可复用并增强。

## 1. 工作流
1) 生成订单草稿（来自调仓建议/操作计划/手工）
2) 风控校验（逐条 + 组合级）→ 输出 PASS/WARN/FAIL
3) 用户确认（展示假设、费用、影响）
4) 执行（模拟撮合）→ 写入订单/成交/持仓/资金
5) 审计落地（草稿、风控结果、确认快照、执行结果）

## 2. 风控规则（V1最小集合）

### 2.1 参数（可配置）
- `max_position_per_symbol`：单票最大仓位（默认 0.25）
- `min_cash_ratio`：最低现金比例（默认 0.05）
- `max_order_value`：单笔最大成交额（默认 200000）
- `price_deviation_limit`：价格偏离限制（默认 0.03）
- `lot_size_stock`：股票最小交易单位（默认 100）
- `lot_size_etf`：ETF最小交易单位（默认 100）

### 2.2 规则清单（示例 code）
- `RISK_NO_PORTFOLIO`：草稿未绑定组合 → FAIL
- `RISK_INVALID_QTY`：数量<=0 或不符合最小交易单位 → FAIL
- `RISK_INSUFFICIENT_CASH`：买入后现金<0 或低于最低现金比例 → FAIL
- `RISK_POSITION_LIMIT`：买入后单票仓位超过上限 → FAIL
- `RISK_MAX_ORDER_VALUE`：单笔成交额超过上限 → WARN（或 FAIL，取决于配置）
- `RISK_PRICE_DEVIATION`：草稿限价相对最新价偏离过大 → WARN
- `RISK_TRADING_STATUS_UNKNOWN`：无法判断停牌/涨跌停 → WARN（不拦截，但提示风险）

## 3. 风控输出结构
- 总状态：PASS/WARN/FAIL
- 明细：
  - `code`：规则编码
  - `level`：PASS/WARN/FAIL
  - `message`：给用户看的原因
  - `suggestion`：可执行建议（如“将数量调整为100的整数倍”）

## 4. 模拟撮合假设（V1）
- 订单类型：默认 LIMIT
- 成交价：
  - 若限价买入：`fill_price = min(limit_price, latest_close_or_last)`（可配置）
  - 若限价卖出：`fill_price = max(limit_price, latest_close_or_last)`
- 手续费：按比例（默认 0.0003）+ 最低5元（可选）
- 滑点：按比例（默认 0.0005）
- 部分成交：V1 可简化为一次性全成交（后续可扩展）

## 5. 关键审计点
- `OrderDraft` 创建/编辑/删除
- `RiskCheckResult` 生成
- 用户确认动作（确认人、确认时间、确认前草稿快照）
- 执行结果（订单/成交/费用/持仓变更）

