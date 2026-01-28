# TODO List（本地智能投资工作台 / A股）

- 版本：v0.1
- 说明：本文件是可执行的开发清单；细节参见 `docs/PRD.md`。
- 最近更新：2026-01-27（补齐“一键启动/验证”可用性：start_p0_demo.ps1 显式设置 WORKBENCH_ROOT/DB_PATH、创建 .venv、仅清理自身 jobs；端到端脚本去掉 emoji 以避免 Windows/GBK UnicodeEncodeError，并支持 WORKBENCH_API_BASE 覆盖端口；补充 vnpy_rpc 可选接入文档/脚本与不可用时返回 409）

## 当前进度快照（非验收）

- 勾选表示：仓库内已存在可运行实现/接口/脚本（通常可在 `tests/` 或 `docs/DEV.md` 找到验证方式）；不等同于“已验收/已融合”。
- 目前主要缺口：P2（FinRL/策略体系深化）与更真实的实盘网关部署（vn.py 网关通常需要额外安装与券商环境）。
- UI 基线已收敛：StockAnal_Sys 全站使用 theme.css + ui.css 提供统一 tokens/卡片/表格/表单外观，并补齐 window.App 请求封装。

## P0（必须完成：跑通“选股→研究→组合→模拟下单确认→复盘”闭环）

### P0-基础与数据层

- [x] P0-01 统一领域模型（字段口径、枚举、时间/单位、主键规则）
- [x] P0-02 SQLite Schema 设计 + 迁移机制
- [x] P0-03 数据源适配器框架（可插拔接口、注册机制、统一异常/限流/重试）
- [x] P0-04 AKShare Provider（字段映射、质量标记、降级策略）
- [x] P0-05 TuShare Provider（token配置、限频控制、回退AKShare）
- [x] P0-06 数据更新/缓存/任务调度（增量、断点续跑、失败重试）
- [x] P0-07 配置与密钥管理（分层配置、校验提示、敏感信息不落日志）
- [x] P0-08 后端 API 规范与错误模型（分页/排序/过滤/错误码）
- [x] P0-09 审计与可追溯（评分/计划/调仓/确认链路快照）

### P0-页面与闭环

- [x] P0-10 Web应用骨架与导航（StockAnal_Sys基座、统一请求/错误提示）
- [x] P0-11 标的与自选/观察/黑名单/标签管理
- [x] P0-12 雷达：Universe 与条件构建器（模板可保存）
- [x] P0-13 雷达：异步扫描任务 + 结果页（命中原因、导出、跳转工作台）
- [x] P0-14 评分引擎 v1（可配置权重 + 可解释拆分）
- [x] P0-15 个股工作台聚合 API（workspace一口拿全景数据 + 数据版本）
- [x] P0-16 工作台：K线与技术指标展示（复权/参数标注）
- [x] P0-17 工作台：基本面/估值摘要卡（缺失降级）
- [x] P0-18 工作台：资金流 + 新闻/公告（收藏、引用）
- [x] P0-19 操作计划生成器 v1（结构化、可编辑、可版本化、可生成草稿）
- [x] P0-20 研究纪要与引用回链（导出Markdown）
- [x] P0-21 组合基础（多组合、持仓/流水录入与CSV导入）
- [x] P0-22 组合分析与预警 v1（阈值可配、预警中心）
- [x] P0-23 调仓建议 → 订单草稿（影响评估、草稿可编辑）
- [x] P0-24 下单确认与风控校验 v1（模拟通道）
- [x] P0-25 交易台账（订单/成交/持仓变更/导出）
- [x] P0-26 端到端验收用例（最小闭环脚本/清单，可复现；支持 `WORKBENCH_API_BASE` 覆盖端口；无 emoji 输出以兼容 Windows/GBK 控制台）
- [x] P0-27 本地启动与健康检查（10分钟跑起来；`start_p0_demo.ps1` 会创建/复用 `.venv`，并显式设置 `WORKBENCH_ROOT/WORKBENCH_DB_PATH`）

## P1（增强：实盘半自动 + AI研究助理）


P1 验证方式（最小可复现）

- Live trading facade：GET /api/v1/live/info，POST /api/v1/live/ping；sim 模式可用 POST /api/v1/live/orders（会走草稿+风控，可选 auto_confirm）。
- vnpy_rpc（可选）：安装 `workbench/requirements_vnpy_rpc.txt`（pyzmq）并启动外部 RPC server（见 `docs/VNPY_RPC.md`）；未满足条件时相关 /api/v1/live/* 返回 409（LIVE_NOT_AVAILABLE）。
- 盘中监控：POST /api/v1/monitor/run + GET /api/v1/monitor/alerts（配合 /api/v1/monitor/rules 管理规则）。
- AI 研究助理：POST /api/v1/assistant/chat（StockAnal_Sys 的 /research 页面已接入；save_note=true 将写入 notes 并返回 note_id）。
- 本地知识库：POST /api/v1/kb/documents、GET /api/v1/kb/search；也可用 POST /api/v1/kb/ingest/news|notes 将现有数据导入 KB。
- 报告与回测：POST /api/v1/reports/stock|portfolio|trades；POST /api/v1/backtest/run|compare。
- [x] vnpy 实盘接入（默认 sim；可选 vnpy_rpc 适配器对接外部 vn.py RPC 服务；需要额外安装 pyzmq 并启动 RPC server，详见 `docs/VNPY_RPC.md`）
- [x] 风控规则库增强（价格偏离、单日限额、重复下单防抖等可配置）
- [x] 盘中监控与提醒（触发条件、预警中心联动）
- [x] DeepResearch：AI研究助理（结论+依据+风险点+引用，写入纪要）
- [x] 本地知识库（导入研报/公告/笔记，离线检索与引用）
- [x] 报告导出（个股研究报告、组合月报、交易复盘）
- [x] 历史回放/轻量回测（对评分/信号/调仓建议做回测）

## P2（智能与量化深化：FinRL 与策略体系）

- [ ] FinRL 本地研究管线：数据准备→训练→验证→产出信号（不直连下单）
- [ ] 策略/信号注册与版本管理（参数、数据快照、报告、可回滚）
- [ ] 因子工程与因子库（缺失/标准化/去极值/中性化等）
- [ ] 组合优化（风险约束下给出调仓建议）
- [ ] 更精细交易成本模型（用于模拟/回测更贴近真实）
- [ ] 插件生态（更多数据源/更多交易网关/更多图表指标）

## Definition of Done（对任一勾选项的最低要求）

- 有清晰输入/输出与错误处理
- 有最小可复现的验证方式（脚本/页面/接口）
- 不破坏“本地单机、可插拔、可追溯、半自动确认”的产品边界
