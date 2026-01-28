# 版本更新记录

## v2.1.2 (2025-12-16)

### 数据接口双层冗余架构
- **新增adapters层**：实现数据源适配器模式
  - `akshare_adapter.py` - akshare适配器，含东财→腾讯内部冗余
  - `baostock_adapter.py` - baostock备用适配器
  - `base_adapter.py` - 适配器基类
- **新增DataProvider统一数据层**：封装多数据源故障转移
- **新增FallbackManager**：自动故障转移管理器
- **改造6个分析模块**接入DataProvider：
  - stock_analyzer.py
  - fundamental_analyzer.py
  - index_industry_analyzer.py
  - capital_flow_analyzer.py
  - industry_analyzer.py
  - etf_analyzer.py

### Bug修复
- 修复情景预测AI分析JSON解析失败问题（支持```json代码块格式）
- 修复概念板块成分股显示问题
- 移除mock数据降级，API无数据时返回空数组

---

## v2.1.1

- **Issue #34 修复**: TradingAgentsGraph.propagate()参数兼容性问题，使用inspect动态检查方法签名
- **Issue #29 新增**: 市场扫描按板块扫描功能（科创50/100、北证50），使用指数成分股接口增强稳定性
- **Issue #31 新增**: 智能问答历史记录功能，LocalStorage保存查询记录和对话内容
- 新增板块股票API：`/api/board_stocks`

---

## v2.1.0

- 重构项目为模块化架构（app/analysis、app/web、app/core）
- 新增ETF分析功能，支持ETF基金评估和持仓分析
- 新增Agent智能分析功能，基于AI Agent的深度分析
- 新增认证中间件，增强系统安全性
- 优化缓存机制，增加市场收盘时自动清理缓存
- 增强错误处理和系统稳定性
- 新增智能问答功能，支持联网搜索实时信息和多轮对话
- 优化情景预测模块，提高预测精度和可视化效果
- 新增行业分析功能
- 改进首页为财经门户风格，实时显示财经要闻与舆情热点
- 增加全球主要市场状态实时监控
- 优化服务器超时处理
- 改进UI交互体验

---

## v2.0.0

- 增加多维度分析能力
- 整合AI API实现AI增强分析
- 新增投资组合管理功能
- 重构用户界面，添加交互式图表
- 优化技术分析和评分系统

---

## v1.0.0 (初始版本)

- 基础股票分析功能
- 技术指标计算
- 简单评分系统
- 基础Web界面
