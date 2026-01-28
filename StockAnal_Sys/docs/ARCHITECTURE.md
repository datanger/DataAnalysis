# 系统架构文档

本文档详细描述了智能股票分析系统的架构设计，旨在为开发人员提供清晰的指导，以便进行后续的维护和功能扩展。

## 1. 概览

系统采用模块化的分层架构，主要由**表现层 (Presentation Layer)**、**应用层 (Application Layer)**、**核心逻辑层 (Core Logic Layer)** 和 **数据层 (Data Layer)** 构成。这种设计旨在实现高内聚、低耦合，使系统更易于扩展和维护。

## 2. 目录结构

```
/
|-- app/                    # 核心应用代码
|   |-- analysis/           # 分析模块
|   |   |-- stock_analyzer.py
|   |   |-- fundamental_analyzer.py
|   |   |-- ...
|   |-- core/               # 核心组件 (如数据库)
|   |   |-- database.py
|   |-- web/                # Web服务 (Flask)
|   |   |-- web_server.py
|   |   |-- templates/
|   |   |-- static/
|-- configs/                # 配置文件
|-- data/                   # 数据文件 (日志、缓存、数据库)
|-- docs/                   # 项目文档
|-- scripts/                # 脚本 (启动、部署)
|-- tradingagents/          # 智能体交易模块
|-- run.py                  # 应用入口
|-- requirements.txt        # Python依赖
|-- .env                    # 环境变量
```

## 3. 分层架构

### 3.1. 表现层 (Presentation Layer)

- **组件**: `app/web/templates/` 和 `app/web/static/`
- **职责**: 负责用户界面的渲染和交互。使用 **Flask** 的模板引擎（Jinja2）动态生成HTML页面，并通过JavaScript、CSS和图像等静态资源提供丰富的用户体验。

### 3.2. 应用层 (Application Layer)

- **组件**: `app/web/web_server.py`, `run.py`
- **职责**: 作为系统的入口，处理HTTP请求和响应。
    - **`web_server.py`**: 定义了所有API端点和Web路由。它负责解析用户请求，调用核心逻辑层的服务，并将结果返回给表现层。
    - **`run.py`**: 应用的启动脚本，负责初始化和运行Flask服务。

### 3.3. 核心逻辑层 (Core Logic Layer)

- **组件**: `app/analysis/`, `app/core/`, `tradingagents/`
- **职责**: 实现系统的核心业务逻辑，包括数据分析、模型计算和第三方服务集成。
    - **`app/analysis/`**: 包含多个独立的分析模块，每个模块负责一个特定的分析领域（如技术分析、基本面分析、资金流分析等）。这种设计使得每个分析功能都可以独立开发和测试。
    - **`app/core/`**: 提供核心共享组件，例如数据库连接和会话管理 (`database.py`)。
    - **`tradingagents/`**: 一个独立的模块，用于实现更复杂的智能体分析功能。

### 3.4. 数据层 (Data Layer)

- **组件**: `data/`, `akshare` (第三方库)
- **职责**: 负责数据的持久化存储和访问。
    - **`data/`**: 存储应用的持久化数据，包括：
        - `stock_analyzer.db`: SQLite数据库文件。
        - `logs/`: 应用日志。
        - `news/`: 缓存的新闻数据。
    - **`akshare`**: 作为主要的数据源，提供股票市场数据。

## 4. 关键流程

### 4.1. 应用启动流程

1. 用户执行 `scripts/start.sh` 脚本。
2. 脚本运行 `run.py`。
3. `run.py` 导入并启动 `app/web/web_server.py` 中的Flask应用。
4. Flask应用初始化所有路由和核心服务。

### 4.2. 用户请求处理流程 (以股票分析为例)

1. 用户在前端页面提交股票分析请求。
2. JavaScript将请求发送到 `web_server.py` 中定义的API端点 (例如 `/api/start_stock_analysis`)。
3. `web_server.py` 接收请求，并调用 `app/analysis/stock_analyzer.py` 中的分析方法。
4. `stock_analyzer.py` 通过 `akshare` 获取数据，进行计算和分析。
5. 分析结果返回给 `web_server.py`。
6. `web_server.py` 将结果格式化为JSON，并返回给前端。
7. 前端JavaScript接收到JSON数据，并动态更新页面内容。

## 5. 设计原则

- **模块化**: 将系统划分为多个独立的模块，每个模块都有明确的职责。
- **分层**: 通过分层架构，将UI、业务逻辑和数据访问分离。
- **可扩展性**: 易于添加新的分析模块或更换数据源，而无需修改系统的核心结构。
- **可维护性**: 清晰的代码结构和文档，便于开发者理解和维护。
