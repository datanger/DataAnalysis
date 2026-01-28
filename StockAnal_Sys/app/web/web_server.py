# -*- coding: utf-8 -*-
"""
智能分析系统（股票） - 股票市场数据分析系统
修改：熊猫大侠
版本：v2.1.0
"""
# web_server.py

import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for
from app.analysis.stock_analyzer import StockAnalyzer
from app.analysis.us_stock_service import USStockService
import threading
import logging
from logging.handlers import RotatingFileHandler
import traceback
import os
import json
from datetime import date, datetime, timedelta
from flask_cors import CORS
from pathlib import Path
import time
try:
    # Optional dependency: the UI can run without caching for preview/development.
    from flask_caching import Cache
except ModuleNotFoundError:  # pragma: no cover
    Cache = None
import threading
import sys
try:
    # Optional dependency: only used to serve Swagger UI under /api/docs.
    from flask_swagger_ui import get_swaggerui_blueprint
except ModuleNotFoundError:  # pragma: no cover
    get_swaggerui_blueprint = None
from app.core.database import get_session, StockInfo, AnalysisResult, Portfolio, USE_DATABASE
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False
from app.analysis.industry_analyzer import IndustryAnalyzer
from app.analysis.fundamental_analyzer import FundamentalAnalyzer
from app.analysis.capital_flow_analyzer import CapitalFlowAnalyzer
from app.analysis.scenario_predictor import ScenarioPredictor
from app.analysis.stock_qa import StockQA
from app.analysis.risk_monitor import RiskMonitor
from app.analysis.index_industry_analyzer import IndexIndustryAnalyzer
from app.analysis.news_fetcher import news_fetcher, start_news_scheduler
try:
    from app.analysis.etf_analyzer import EtfAnalyzer
except ModuleNotFoundError:  # pragma: no cover
    EtfAnalyzer = None

import sys
import os

# 将 tradingagents 目录添加到系统路径
# 这允许应用从 tradingagents 代码库中导入模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../tradingagents')))


# 加载环境变量
load_dotenv()

# 检查是否需要初始化数据库
if USE_DATABASE:
    init_db()

# 配置Swagger（可选）
SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'
swaggerui_blueprint = None
if get_swaggerui_blueprint is not None:
    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        API_URL,
        config={
            'app_name': "股票智能分析系统 API文档"
        }
    )

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
analyzer = StockAnalyzer()
us_stock_service = USStockService()

# Allow the UI to point at a non-default Workbench API (useful when port 8000 is occupied).
# Priority: explicit WORKBENCH_API_BASE > derived from WORKBENCH_HOST/WORKBENCH_PORT.
_wb_api = (os.getenv("WORKBENCH_API_BASE") or "").strip()
if not _wb_api:
    _wb_host = (os.getenv("WORKBENCH_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    _wb_port = (os.getenv("WORKBENCH_PORT") or "8000").strip() or "8000"
    _wb_api = f"http://{_wb_host}:{_wb_port}/api/v1"
app.config["WORKBENCH_API_BASE"] = _wb_api

# 配置缓存
cache_config = {
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300
}

# 如果配置了Redis，使用Redis作为缓存后端
if os.getenv('USE_REDIS_CACHE', 'False').lower() == 'true' and os.getenv('REDIS_URL'):
    cache_config = {
        'CACHE_TYPE': 'RedisCache',
        'CACHE_REDIS_URL': os.getenv('REDIS_URL'),
        'CACHE_DEFAULT_TIMEOUT': 300
    }

if Cache is not None:
    cache = Cache(config=cache_config)
    cache.init_app(app)
else:
    class _NoopCache:
        def init_app(self, _app):
            return None

        def cached(self, *args, **kwargs):
            def _decorator(fn):
                return fn
            return _decorator

        def memoize(self, *args, **kwargs):
            def _decorator(fn):
                return fn
            return _decorator

    cache = _NoopCache()

if swaggerui_blueprint is not None:
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)


# 确保全局变量在重新加载时不会丢失
if 'analyzer' not in globals():
    try:
        from app.analysis.stock_analyzer import StockAnalyzer

        analyzer = StockAnalyzer()
        print("成功初始化全局StockAnalyzer实例")
    except Exception as e:
        print(f"初始化StockAnalyzer时出错: {e}", file=sys.stderr)
        raise

# 初始化模块实例
fundamental_analyzer = FundamentalAnalyzer()
capital_flow_analyzer = CapitalFlowAnalyzer()
scenario_predictor = ScenarioPredictor(analyzer, os.getenv('OPENAI_API_KEY'), os.getenv('OPENAI_API_MODEL'))
stock_qa = StockQA(analyzer, os.getenv('OPENAI_API_KEY'))
risk_monitor = RiskMonitor(analyzer)
index_industry_analyzer = IndexIndustryAnalyzer(analyzer)
industry_analyzer = IndustryAnalyzer()

start_news_scheduler()

# 线程本地存储
thread_local = threading.local()


def get_analyzer():
    """获取线程本地的分析器实例"""
    # 如果线程本地存储中没有分析器实例，创建一个新的
    if not hasattr(thread_local, 'analyzer'):
        thread_local.analyzer = StockAnalyzer()
    return thread_local.analyzer


# 配置日志
# 从环境变量读取日志级别和文件路径
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_file = os.getenv('LOG_FILE', 'data/logs/server.log')

# 确保日志目录存在
os.makedirs(os.path.dirname(log_file), exist_ok=True)

# 创建日志格式化器
formatter = logging.Formatter(
    '[%(asctime)s] [%(process)d:%(thread)d] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# 清除所有现有的处理器，以避免重复日志
if root_logger.hasHandlers():
    root_logger.handlers.clear()

# 添加文件处理器
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*10, backupCount=5, encoding='utf-8') # 10MB
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# 添加控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# 将Flask的默认处理器移除，使其日志也遵循我们的配置
from flask.logging import default_handler
app.logger.removeHandler(default_handler)
app.logger.propagate = True

# 将 werkzeug 日志记录器的级别也设置为 .env 中定义的级别
logging.getLogger('werkzeug').setLevel(log_level)

app.logger.info(f"日志系统已初始化，级别: {log_level}, 文件: {log_file}")


# 扩展任务管理系统以支持不同类型的任务
task_types = {
    'scan': 'market_scan',  # 市场扫描任务
    'analysis': 'stock_analysis',  # 个股分析任务
    'agent_analysis': 'agent_analysis', # 智能体分析任务
    'etf_analysis': 'etf_analysis' # ETF分析任务
}

# 任务数据存储
tasks = {
    'market_scan': {},
    'stock_analysis': {},
    'etf_analysis': {},
}



def get_task_store(task_type):
    """获取指定类型的任务存储"""
    return tasks.get(task_type, {})


def generate_task_key(task_type, **params):
    """生成任务键"""
    if task_type == 'stock_analysis':
        # 对于个股分析，使用股票代码和市场类型作为键
        return f"{params.get('stock_code')}_{params.get('market_type', 'A')}"
    if task_type == 'etf_analysis':
        return f"{params.get('etf_code')}"
    return None  # 其他任务类型不使用预生成的键


def get_or_create_task(task_type, **params):
    """获取或创建任务"""
    store = get_task_store(task_type)
    task_key = generate_task_key(task_type, **params)

    # 检查是否有现有任务
    if task_key and task_key in store:
        task = store[task_key]
        # 检查任务是否仍然有效
        if task['status'] in [TASK_PENDING, TASK_RUNNING]:
            return task['id'], task, False
        if task['status'] == TASK_COMPLETED and 'result' in task:
            # 任务已完成且有结果，重用它
            return task['id'], task, False

    # 创建新任务
    task_id = generate_task_id()
    task = {
        'id': task_id,
        'key': task_key,  # 存储任务键以便以后查找
        'type': task_type,
        'status': TASK_PENDING,
        'progress': 0,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'params': params
    }

    with task_lock:
        if task_key:
            store[task_key] = task
        store[task_id] = task

    return task_id, task, True


# 添加到web_server.py顶部
# 任务管理系统
scan_tasks = {}  # 存储扫描任务的状态和结果
task_lock = threading.Lock()  # 用于线程安全操作


# 自定义异常，用于任务取消
class TaskCancelledException(Exception):
    pass

# 任务状态常量
TASK_PENDING = 'pending'
TASK_RUNNING = 'running'
TASK_COMPLETED = 'completed'
TASK_FAILED = 'failed'
TASK_CANCELLED = 'cancelled'


def generate_task_id():
    """生成唯一的任务ID"""
    import uuid
    return str(uuid.uuid4())


def start_market_scan_task_status(task_id, status, progress=None, result=None, error=None):
    """更新任务状态 - 保持原有签名"""
    with task_lock:
        if task_id in scan_tasks:
            task = scan_tasks[task_id]
            task['status'] = status
            if progress is not None:
                task['progress'] = progress
            if result is not None:
                task['result'] = result
            if error is not None:
                task['error'] = error
            task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def update_task_status(task_type, task_id, status, progress=None, result=None, error=None):
    """更新任务状态"""
    with task_lock:
        task = None
        if task_type == 'agent_analysis':
            task = agent_session_manager.load_task(task_id)
        else:
            store = get_task_store(task_type)
            if task_id in store:
                task = store.get(task_id)

        if not task:
            app.logger.warning(f"更新任务状态时未找到任务: {task_id} (类型: {task_type})")
            return

        # 更新任务属性
        task['status'] = status
        if progress is not None:
            task['progress'] = progress
        if result is not None:
            if 'result' not in task or not isinstance(task['result'], dict):
                task['result'] = {}
            task['result'].update(result)
        if error is not None:
            task['error'] = error
        task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 保存更新后的任务
        if task_type == 'agent_analysis':
            agent_session_manager.save_task(task)
        else:
            # 更新键索引的任务 (如果适用)
            store = get_task_store(task_type)
            if 'key' in task and task.get('key') and task['key'] in store:
                store[task['key']] = task
            store[task_id] = task # also save by id


analysis_tasks = {}


def get_or_create_analysis_task(stock_code, market_type='A'):
    """获取或创建个股分析任务"""
    # 创建一个键，用于查找现有任务
    task_key = f"{stock_code}_{market_type}"

    with task_lock:
        # 检查是否有现有任务
        for task_id, task in analysis_tasks.items():
            if task.get('key') == task_key:
                # 检查任务是否仍然有效
                if task['status'] in [TASK_PENDING, TASK_RUNNING]:
                    return task_id, task, False
                if task['status'] == TASK_COMPLETED and 'result' in task:
                    # 任务已完成且有结果，重用它
                    return task_id, task, False

        # 创建新任务
        task_id = generate_task_id()
        task = {
            'id': task_id,
            'key': task_key,
            'status': TASK_PENDING,
            'progress': 0,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'params': {
                'stock_code': stock_code,
                'market_type': market_type
            }
        }

        analysis_tasks[task_id] = task

        return task_id, task, True


def update_analysis_task(task_id, status, progress=None, result=None, error=None):
    """更新个股分析任务状态"""
    with task_lock:
        if task_id in analysis_tasks:
            task = analysis_tasks[task_id]
            task['status'] = status
            if progress is not None:
                task['progress'] = progress
            if result is not None:
                task['result'] = result
            if error is not None:
                task['error'] = error
            task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# 定义自定义JSON编码器


# 在web_server.py中，更新convert_numpy_types函数以处理NaN值

# 将NumPy类型转换为Python原生类型的函数
def convert_numpy_types(obj):
    """递归地将字典和列表中的NumPy类型转换为Python原生类型"""
    try:
        import numpy as np
        import math

        if isinstance(obj, dict):
            return {convert_numpy_types(key): convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            # Handle NaN and Infinity specifically
            if np.isnan(obj):
                return None
            elif np.isinf(obj):
                return None if obj < 0 else 1e308  # Use a very large number for +Infinity
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        # Handle Python's own float NaN and Infinity
        elif isinstance(obj, float):
            if math.isnan(obj):
                return None
            elif math.isinf(obj):
                return None
            return obj
        # 添加对date和datetime类型的处理
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        else:
            return obj
    except ImportError:
        # 如果没有安装numpy，但需要处理date和datetime
        import math
        if isinstance(obj, dict):
            return {convert_numpy_types(key): convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        # Handle Python's own float NaN and Infinity
        elif isinstance(obj, float):
            if math.isnan(obj):
                return None
            elif math.isinf(obj):
                return None
            return obj
        return obj


# 同样更新 NumpyJSONEncoder 类
class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Handle LangChain message objects first
        try:
            from langchain_core.messages import BaseMessage
            if isinstance(obj, BaseMessage):
                return {"type": obj.__class__.__name__, "content": str(obj.content)}
        except ImportError:
            pass  # If langchain is not installed, just proceed

        # For NumPy data types
        try:
            import numpy as np
            import math
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                # Handle NaN and Infinity specifically
                if np.isnan(obj):
                    return None
                elif np.isinf(obj):
                    return None
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.bool_):
                return bool(obj)
            # Handle Python's own float NaN and Infinity
            elif isinstance(obj, float):
                if math.isnan(obj):
                    return None
                elif math.isinf(obj):
                    return None
                return obj
        except ImportError:
            # Handle Python's own float NaN and Infinity if numpy is not available
            import math
            if isinstance(obj, float):
                if math.isnan(obj):
                    return None
                elif math.isinf(obj):
                    return None

        # 添加对date和datetime类型的处理
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()

        # Fallback for other non-serializable types
        try:
            return super(NumpyJSONEncoder, self).default(obj)
        except TypeError:
            # For LangChain messages or other complex objects, convert to string
            return str(obj)


# Helper to convert LangChain messages to JSON serializable format
def convert_messages_to_dict(obj):
    """Recursively convert LangChain message objects to dictionaries."""
    # Check if langchain_core is available and if the object is a message
    try:
        from langchain_core.messages import BaseMessage
        is_message = isinstance(obj, BaseMessage)
    except ImportError:
        is_message = False

    if is_message:
        # Base case: convert message object to dict
        return {"type": obj.__class__.__name__, "content": str(obj.content)}
    elif isinstance(obj, dict):
        # Recursive step for dictionaries
        return {k: convert_messages_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        # Recursive step for lists
        return [convert_messages_to_dict(elem) for elem in obj]
    else:
        # Return the object as is if no conversion is needed
        return obj


# 使用我们的编码器的自定义 jsonify 函数
def custom_jsonify(data):
    return app.response_class(
        json.dumps(convert_numpy_types(data), cls=NumpyJSONEncoder),
        mimetype='application/json'
    )


# 保持API兼容的路由
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/news')
def news():
    return render_template('news.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        stock_codes = data.get('stock_codes', [])
        market_type = data.get('market_type', 'A')

        if not stock_codes:
            return jsonify({'error': '请输入代码'}), 400

        app.logger.info(f"分析股票请求: {stock_codes}, 市场类型: {market_type}")

        # 设置最大处理时间，每只股票10秒
        max_time_per_stock = 10  # 秒
        max_total_time = max(30, min(60, len(stock_codes) * max_time_per_stock))  # 至少30秒，最多60秒

        start_time = time.time()
        results = []

        for stock_code in stock_codes:
            try:
                # 检查是否已超时
                if time.time() - start_time > max_total_time:
                    app.logger.warning(f"分析股票请求已超过{max_total_time}秒，提前返回已处理的{len(results)}只股票")
                    break

                # 使用线程本地缓存的分析器实例
                current_analyzer = get_analyzer()
                result = current_analyzer.quick_analyze_stock(stock_code.strip(), market_type)

                app.logger.info(
                    f"分析结果: 股票={stock_code}, 名称={result.get('stock_name', '未知')}, 行业={result.get('industry', '未知')}")
                results.append(result)
            except Exception as e:
                app.logger.error(f"分析股票 {stock_code} 时出错: {str(e)}")
                results.append({
                    'stock_code': stock_code,
                    'error': str(e),
                    'stock_name': '分析失败',
                    'industry': '未知'
                })

        return jsonify({'results': results})
    except Exception as e:
        app.logger.error(f"分析股票时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/north_flow_history', methods=['POST'])
def api_north_flow_history():
    try:
        data = request.json
        stock_code = data.get('stock_code')
        days = data.get('days', 10)  # 默认为10天，对应前端的默认选项

        # 计算 end_date 为当前时间
        end_date = datetime.now().strftime('%Y%m%d')

        # 计算 start_date 为 end_date 减去指定的天数
        start_date = (datetime.now() - timedelta(days=int(days))).strftime('%Y%m%d')

        if not stock_code:
            return jsonify({'error': '请提供股票代码'}), 400

        # 调用北向资金历史数据方法

        analyzer = CapitalFlowAnalyzer()
        result = analyzer.get_north_flow_history(stock_code, start_date, end_date)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"获取北向资金历史数据出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/search_us_stocks', methods=['GET'])
def search_us_stocks():
    try:
        keyword = request.args.get('keyword', '')
        if not keyword:
            return jsonify({'error': '请输入搜索关键词'}), 400

        results = us_stock_service.search_us_stocks(keyword)
        return jsonify({'results': results})

    except Exception as e:
        app.logger.error(f"搜索美股代码时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 新增可视化分析页面路由
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/stock_detail/<string:stock_code>')
def stock_detail(stock_code):
    market_type = request.args.get('market_type', 'A')
    return render_template('stock_detail.html', stock_code=stock_code, market_type=market_type)


@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html')


@app.route('/market_scan')
def market_scan():
    # Direct replacement: unify all stock-selection pages into a single workbench.
    return redirect(url_for('workbench'))


@app.route('/workbench')
def workbench():
    return render_template('workbench.html')


# 基本面分析页面
@app.route('/fundamental')
def fundamental():
    return render_template('fundamental.html')


# 资金流向页面
@app.route('/capital_flow')
def capital_flow():
    return render_template('capital_flow.html')


# 情景预测页面
@app.route('/scenario_predict')
def scenario_predict():
    return render_template('scenario_predict.html')


# 风险监控页面
@app.route('/risk_monitor')
def risk_monitor_page():
    return render_template('risk_monitor.html')


# 智能问答页面
@app.route('/qa')
def qa_page():
    # 功能合并：统一到研究中心
    return redirect(url_for('research_center'))


# 行业分析页面
@app.route('/industry_analysis')
def industry_analysis():
    return render_template('industry_analysis.html')



# 智能体分析页面
@app.route('/agent_analysis')
def agent_analysis_page():
    # 功能合并：统一到研究中心
    return redirect(url_for('research_center'))


@app.route('/research')
def research_center():
    return render_template('research.html')


@app.route('/etf_analysis')
def etf_analysis_page():
    return render_template('etf_analysis.html')





def make_cache_key_with_stock():
    """创建包含股票代码的自定义缓存键"""
    path = request.path

    # 从请求体中获取股票代码
    stock_code = None
    if request.is_json:
        stock_code = request.json.get('stock_code')

    # 构建包含股票代码的键
    if stock_code:
        return f"{path}_{stock_code}"
    else:
        return path


@app.route('/api/start_stock_analysis', methods=['POST'])
def start_stock_analysis():
    """启动个股分析任务"""
    try:
        data = request.json
        stock_code = data.get('stock_code')
        market_type = data.get('market_type', 'A')

        if not stock_code:
            return jsonify({'error': '请输入股票代码'}), 400

        app.logger.info(f"准备分析股票: {stock_code}")

        # 获取或创建任务
        task_id, task, is_new = get_or_create_task(
            'stock_analysis',
            stock_code=stock_code,
            market_type=market_type
        )

        # 如果是已完成的任务，直接返回结果
        if task['status'] == TASK_COMPLETED and 'result' in task:
            app.logger.info(f"使用缓存的分析结果: {stock_code}")
            return jsonify({
                'task_id': task_id,
                'status': task['status'],
                'result': task['result']
            })

        # 如果是新创建的任务，启动后台处理
        if is_new:
            app.logger.info(f"创建新的分析任务: {task_id}")

            # 启动后台线程执行分析
            def run_analysis():
                try:
                    update_task_status('stock_analysis', task_id, TASK_RUNNING, progress=10)

                    # 执行分析
                    result = analyzer.perform_enhanced_analysis(stock_code, market_type)

                    # 更新任务状态为完成
                    update_task_status('stock_analysis', task_id, TASK_COMPLETED, progress=100, result=result)
                    app.logger.info(f"分析任务 {task_id} 完成")

                except Exception as e:
                    app.logger.error(f"分析任务 {task_id} 失败: {str(e)}")
                    app.logger.error(traceback.format_exc())
                    update_task_status('stock_analysis', task_id, TASK_FAILED, error=str(e))

            # 启动后台线程
            thread = threading.Thread(target=run_analysis)
            thread.daemon = True
            thread.start()

        # 返回任务ID和状态
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'message': f'已启动分析任务: {stock_code}'
        })

    except Exception as e:
        app.logger.error(f"启动个股分析任务时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis_status/<task_id>', methods=['GET'])
def get_analysis_status(task_id):
    """获取个股分析任务状态"""
    store = get_task_store('stock_analysis')
    with task_lock:
        if task_id not in store:
            return jsonify({'error': '找不到指定的分析任务'}), 404

        task = store[task_id]

        # 基本状态信息
        status = {
            'id': task['id'],
            'status': task['status'],
            'progress': task.get('progress', 0),
            'created_at': task['created_at'],
            'updated_at': task['updated_at']
        }

        # 如果任务完成，包含结果
        if task['status'] == TASK_COMPLETED and 'result' in task:
            status['result'] = task['result']

        # 如果任务失败，包含错误信息
        if task['status'] == TASK_FAILED and 'error' in task:
            status['error'] = task['error']

        return custom_jsonify(status)


@app.route('/api/cancel_analysis/<task_id>', methods=['POST'])
def cancel_analysis(task_id):
    """取消个股分析任务"""
    store = get_task_store('stock_analysis')
    with task_lock:
        if task_id not in store:
            return jsonify({'error': '找不到指定的分析任务'}), 404

        task = store[task_id]

        if task['status'] in [TASK_COMPLETED, TASK_FAILED]:
            return jsonify({'message': '任务已完成或失败，无法取消'})

        # 更新状态为失败
        task['status'] = TASK_FAILED
        task['error'] = '用户取消任务'
        task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 更新键索引的任务
        if 'key' in task and task['key'] in store:
            store[task['key']] = task

        return jsonify({'message': '任务已取消'})


# ETF 分析路由
@app.route('/api/start_etf_analysis', methods=['POST'])
def start_etf_analysis():
    """启动ETF分析任务"""
    try:
        if EtfAnalyzer is None:
            return jsonify({'error': 'ETF 分析模块未安装依赖（stockstats），当前环境暂不可用'}), 501

        data = request.json
        etf_code = data.get('etf_code')

        if not etf_code:
            return jsonify({'error': '请输入ETF代码'}), 400

        app.logger.info(f"准备分析ETF: {etf_code}")

        task_id, task, is_new = get_or_create_task(
            'etf_analysis',
            etf_code=etf_code
        )

        if task['status'] == TASK_COMPLETED and 'result' in task:
            app.logger.info(f"使用缓存的ETF分析结果: {etf_code}")
            return jsonify({
                'task_id': task_id,
                'status': task['status'],
                'result': task['result']
            })

        if is_new:
            app.logger.info(f"创建新的ETF分析任务: {task_id}")

            def run_etf_analysis():
                try:
                    update_task_status('etf_analysis', task_id, TASK_RUNNING, progress=10)
                    
                    # 使用一个新的 EtfAnalyzer 实例, 并传入stock_analyzer
                    etf_analyzer_instance = EtfAnalyzer(etf_code, analyzer)
                    result = etf_analyzer_instance.run_analysis()
                    
                    update_task_status('etf_analysis', task_id, TASK_COMPLETED, progress=100, result=result)
                    app.logger.info(f"ETF分析任务 {task_id} 完成")

                except Exception as e:
                    app.logger.error(f"ETF分析任务 {task_id} 失败: {str(e)}")
                    app.logger.error(traceback.format_exc())
                    update_task_status('etf_analysis', task_id, TASK_FAILED, error=str(e))

            thread = threading.Thread(target=run_etf_analysis)
            thread.daemon = True
            thread.start()

        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'message': f'已启动ETF分析任务: {etf_code}'
        })

    except Exception as e:
        app.logger.error(f"启动ETF分析任务时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/etf_analysis_status/<task_id>', methods=['GET'])
def get_etf_analysis_status(task_id):
    """获取ETF分析任务状态"""
    store = get_task_store('etf_analysis')
    with task_lock:
        if task_id not in store:
            return jsonify({'error': '找不到指定的ETF分析任务'}), 404

        task = store[task_id]

        status = {
            'id': task['id'],
            'status': task['status'],
            'progress': task.get('progress', 0),
            'created_at': task['created_at'],
            'updated_at': task['updated_at']
        }

        if task['status'] == TASK_COMPLETED and 'result' in task:
            status['result'] = task['result']
        
        if task['status'] == TASK_FAILED and 'error' in task:
            status['error'] = task['error']

        return custom_jsonify(status)


# 保留原有API用于向后兼容
@app.route('/api/enhanced_analysis', methods=['POST'])
def enhanced_analysis():
    """原增强分析API的向后兼容版本"""
    try:
        data = request.json
        stock_code = data.get('stock_code')
        market_type = data.get('market_type', 'A')

        if not stock_code:
            return custom_jsonify({'error': '请输入股票代码'}), 400

        # 调用新的任务系统，但模拟同步行为
        # 这会导致和之前一样的超时问题，但保持兼容
        timeout = 300
        start_time = time.time()

        # 获取或创建任务
        task_id, task, is_new = get_or_create_task(
            'stock_analysis',
            stock_code=stock_code,
            market_type=market_type
        )

        # 如果是已完成的任务，直接返回结果
        if task['status'] == TASK_COMPLETED and 'result' in task:
            app.logger.info(f"使用缓存的分析结果: {stock_code}")
            return custom_jsonify({'result': task['result']})

        # 启动分析（如果是新任务）
        if is_new:
            # 同步执行分析
            try:
                result = analyzer.perform_enhanced_analysis(stock_code, market_type)
                update_task_status('stock_analysis', task_id, TASK_COMPLETED, progress=100, result=result)
                app.logger.info(f"分析完成: {stock_code}，耗时 {time.time() - start_time:.2f} 秒")
                return custom_jsonify({'result': result})
            except Exception as e:
                app.logger.error(f"分析过程中出错: {str(e)}")
                update_task_status('stock_analysis', task_id, TASK_FAILED, error=str(e))
                return custom_jsonify({'error': f'分析过程中出错: {str(e)}'}), 500
        else:
            # 已存在正在处理的任务，等待其完成
            max_wait = timeout - (time.time() - start_time)
            wait_interval = 0.5
            waited = 0

            while waited < max_wait:
                with task_lock:
                    current_task = store[task_id]
                    if current_task['status'] == TASK_COMPLETED and 'result' in current_task:
                        return custom_jsonify({'result': current_task['result']})
                    if current_task['status'] == TASK_FAILED:
                        error = current_task.get('error', '任务失败，无详细信息')
                        return custom_jsonify({'error': error}), 500

                time.sleep(wait_interval)
                waited += wait_interval

            # 超时
            return custom_jsonify({'error': '处理超时，请稍后重试'}), 504

    except Exception as e:
        app.logger.error(f"执行增强版分析时出错: {traceback.format_exc()}")
        return custom_jsonify({'error': str(e)}), 500


# 添加在web_server.py主代码中
@app.errorhandler(404)
def not_found(error):
    """处理404错误"""
    if request.path.startswith('/api/'):
        # 为API请求返回JSON格式的错误
        return jsonify({
            'error': '找不到请求的API端点',
            'path': request.path,
            'method': request.method
        }), 404
    # 为网页请求返回HTML错误页
    return render_template('error.html', error_code=404, message="找不到请求的页面"), 404


@app.errorhandler(500)
def server_error(error):
    """处理500错误"""
    app.logger.error(f"服务器错误: {str(error)}")
    if request.path.startswith('/api/'):
        # 为API请求返回JSON格式的错误
        return jsonify({
            'error': '服务器内部错误',
            'message': str(error)
        }), 500
    # 为网页请求返回HTML错误页
    return render_template('error.html', error_code=500, message="服务器内部错误"), 500


# Update the get_stock_data function in web_server.py to handle date formatting properly
@app.route('/api/stock_data', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_stock_data():
    try:
        stock_code = request.args.get('stock_code')
        market_type = request.args.get('market_type', 'A')
        period = request.args.get('period', '1y')  # 默认1年

        if not stock_code:
            return custom_jsonify({'error': '请提供股票代码'}), 400

        # 根据period计算start_date
        end_date = datetime.now().strftime('%Y%m%d')
        if period == '1m':
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        elif period == '3m':
            start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
        elif period == '6m':
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
        elif period == '1y':
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        else:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

        # 获取股票历史数据
        app.logger.info(
            f"获取股票 {stock_code} 的历史数据，市场: {market_type}, 起始日期: {start_date}, 结束日期: {end_date}")
        df = analyzer.get_stock_data(stock_code, market_type, start_date, end_date)

        # 检查数据是否为空
        if df.empty:
            app.logger.warning(f"股票 {stock_code} 的数据为空")
            return custom_jsonify({'error': '未找到股票数据'}), 404

        # 计算技术指标
        app.logger.info(f"计算股票 {stock_code} 的技术指标")
        df = analyzer.calculate_indicators(df)

        # 将DataFrame转为JSON格式
        app.logger.info(f"将数据转换为JSON格式，行数: {len(df)}")

        # 确保日期列是字符串格式 - 修复缓存问题
        if 'date' in df.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(df['date']):
                    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
                else:
                    df = df.copy()
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            except Exception as e:
                app.logger.error(f"处理日期列时出错: {str(e)}")
                df['date'] = df['date'].astype(str)

        # 将NaN值替换为None
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        records = df.to_dict('records')

        app.logger.info(f"数据处理完成，返回 {len(records)} 条记录")
        return custom_jsonify({'data': records})
    except Exception as e:
        app.logger.error(f"获取股票数据时出错: {str(e)}")
        app.logger.error(traceback.format_exc())
        return custom_jsonify({'error': str(e)}), 500


# @app.route('/api/market_scan', methods=['POST'])
# def api_market_scan():
#     try:
#         data = request.json
#         stock_list = data.get('stock_list', [])
#         min_score = data.get('min_score', 60)
#         market_type = data.get('market_type', 'A')

#         if not stock_list:
#             return jsonify({'error': '请提供股票列表'}), 400

#         # 限制股票数量，避免过长处理时间
#         if len(stock_list) > 100:
#             app.logger.warning(f"股票列表过长 ({len(stock_list)}只)，截取前100只")
#             stock_list = stock_list[:100]

#         # 执行市场扫描
#         app.logger.info(f"开始扫描 {len(stock_list)} 只股票，最低分数: {min_score}")

#         # 使用线程池优化处理
#         results = []
#         max_workers = min(10, len(stock_list))  # 最多10个工作线程

#         # 设置较长的超时时间
#         timeout = 300  # 5分钟

#         def scan_thread():
#             try:
#                 return analyzer.scan_market(stock_list, min_score, market_type)
#             except Exception as e:
#                 app.logger.error(f"扫描线程出错: {str(e)}")
#                 return []

#         thread = threading.Thread(target=lambda: results.append(scan_thread()))
#         thread.start()
#         thread.join(timeout)

#         if thread.is_alive():
#             app.logger.error(f"市场扫描超时，已扫描 {len(stock_list)} 只股票超过 {timeout} 秒")
#             return custom_jsonify({'error': '扫描超时，请减少股票数量或稍后再试'}), 504

#         if not results or not results[0]:
#             app.logger.warning("扫描结果为空")
#             return custom_jsonify({'results': []})

#         scan_results = results[0]
#         app.logger.info(f"扫描完成，找到 {len(scan_results)} 只符合条件的股票")

#         # 使用自定义JSON格式处理NumPy数据类型
#         return custom_jsonify({'results': scan_results})
#     except Exception as e:
#         app.logger.error(f"执行市场扫描时出错: {traceback.format_exc()}")
#         return custom_jsonify({'error': str(e)}), 500

@app.route('/api/start_market_scan', methods=['POST'])
def start_market_scan():
    """启动市场扫描任务"""
    try:
        data = request.json
        stock_list = data.get('stock_list', [])
        min_score = data.get('min_score', 60)
        market_type = data.get('market_type', 'A')

        if not stock_list:
            return jsonify({'error': '请提供股票列表'}), 400

        # 限制股票数量，避免过长处理时间
        if len(stock_list) > 100:
            app.logger.warning(f"股票列表过长 ({len(stock_list)}只)，截取前100只")
            stock_list = stock_list[:100]

        # 创建新任务
        task_id = generate_task_id()
        task = {
            'id': task_id,
            'status': TASK_PENDING,
            'progress': 0,
            'total': len(stock_list),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'params': {
                'stock_list': stock_list,
                'min_score': min_score,
                'market_type': market_type
            }
        }

        with task_lock:
            scan_tasks[task_id] = task

        # 启动后台线程执行扫描
        def run_scan():
            try:
                start_market_scan_task_status(task_id, TASK_RUNNING)

                # 执行分批处理
                results = []
                total = len(stock_list)
                batch_size = 10

                for i in range(0, total, batch_size):
                    if task_id not in scan_tasks or scan_tasks[task_id]['status'] != TASK_RUNNING:
                        # 任务被取消
                        app.logger.info(f"扫描任务 {task_id} 被取消")
                        return

                    batch = stock_list[i:i + batch_size]
                    batch_results = []

                    for stock_code in batch:
                        try:
                            report = analyzer.quick_analyze_stock(stock_code, market_type)
                            if report['score'] >= min_score:
                                batch_results.append(report)
                        except Exception as e:
                            app.logger.error(f"分析股票 {stock_code} 时出错: {str(e)}")
                            continue

                    results.extend(batch_results)

                    # 更新进度
                    progress = min(100, int((i + len(batch)) / total * 100))
                    start_market_scan_task_status(task_id, TASK_RUNNING, progress=progress)

                # 按得分排序
                results.sort(key=lambda x: x['score'], reverse=True)

                # 更新任务状态为完成
                start_market_scan_task_status(task_id, TASK_COMPLETED, progress=100, result=results)
                app.logger.info(f"扫描任务 {task_id} 完成，找到 {len(results)} 只符合条件的股票")

            except Exception as e:
                app.logger.error(f"扫描任务 {task_id} 失败: {str(e)}")
                app.logger.error(traceback.format_exc())
                start_market_scan_task_status(task_id, TASK_FAILED, error=str(e))

        # 启动后台线程
        thread = threading.Thread(target=run_scan)
        thread.daemon = True
        thread.start()

        return jsonify({
            'task_id': task_id,
            'status': 'pending',
            'message': f'已启动扫描任务，正在处理 {len(stock_list)} 只股票'
        })

    except Exception as e:
        app.logger.error(f"启动市场扫描任务时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/scan_status/<task_id>', methods=['GET'])
def get_scan_status(task_id):
    """获取扫描任务状态"""
    with task_lock:
        if task_id not in scan_tasks:
            return jsonify({'error': '找不到指定的扫描任务'}), 404

        task = scan_tasks[task_id]

        # 基本状态信息
        status = {
            'id': task['id'],
            'status': task['status'],
            'progress': task.get('progress', 0),
            'total': task.get('total', 0),
            'created_at': task['created_at'],
            'updated_at': task['updated_at']
        }

        # 如果任务完成，包含结果
        if task['status'] == TASK_COMPLETED and 'result' in task:
            status['result'] = task['result']

        # 如果任务失败，包含错误信息
        if task['status'] == TASK_FAILED and 'error' in task:
            status['error'] = task['error']

        return custom_jsonify(status)


@app.route('/api/cancel_scan/<task_id>', methods=['POST'])
def cancel_scan(task_id):
    """取消扫描任务"""
    with task_lock:
        if task_id not in scan_tasks:
            return jsonify({'error': '找不到指定的扫描任务'}), 404

        task = scan_tasks[task_id]

        if task['status'] in [TASK_COMPLETED, TASK_FAILED]:
            return jsonify({'message': '任务已完成或失败，无法取消'})

        # 更新状态为失败
        task['status'] = TASK_FAILED
        task['error'] = '用户取消任务'
        task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({'message': '任务已取消'})


@app.route('/api/index_stocks', methods=['GET'])
def get_index_stocks():
    """获取指数成分股 - 使用DataProvider统一数据层"""
    try:
        from app.core.data_provider import get_data_provider
        data_provider = get_data_provider()
        index_code = request.args.get('index_code', '000300')  # 默认沪深300

        # 获取指数成分股
        app.logger.info(f"获取指数 {index_code} 成分股")
        if index_code not in ['000300', '000905', '000852', '000001']:
            return jsonify({'error': '不支持的指数代码'}), 400

        stock_list = data_provider.get_index_stocks(index_code)
        app.logger.info(f"找到 {len(stock_list)} 只成分股")

        return jsonify({'stock_list': stock_list})
    except Exception as e:
        app.logger.error(f"获取指数成分股时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/industry_stocks', methods=['GET'])
def get_industry_stocks():
    """获取行业成分股 - 使用DataProvider统一数据层"""
    try:
        from app.core.data_provider import get_data_provider
        data_provider = get_data_provider()
        industry = request.args.get('industry', '')

        if not industry:
            return jsonify({'error': '请提供行业名称'}), 400

        # 获取行业成分股
        app.logger.info(f"获取 {industry} 行业成分股")
        stock_list = data_provider.get_industry_stocks(industry)
        app.logger.info(f"找到 {len(stock_list)} 只 {industry} 行业股票")

        return jsonify({'stock_list': stock_list})
    except Exception as e:
        app.logger.error(f"获取行业成分股时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# Issue #29: 按板块获取股票列表（科创板/创业板/北交所等）
@app.route('/api/board_stocks', methods=['GET'])
def get_board_stocks():
    """获取指定板块的股票列表 - 使用DataProvider统一数据层"""
    try:
        from app.core.data_provider import get_data_provider
        data_provider = get_data_provider()
        board = request.args.get('board', 'hs300')

        # 板块映射
        board_map = {
            'hs300': ('000300', '沪深300'),
            'zz500': ('000905', '中证500'),
            'zz1000': ('000852', '中证1000'),
            'kc50': ('000688', '科创50'),
            'kc100': ('000698', '科创100'),
            'bj50': ('899050', '北证50'),
        }

        if board not in board_map:
            return jsonify({'error': f'不支持的板块类型: {board}，支持: {list(board_map.keys())}'}), 400

        index_code, index_name = board_map[board]
        app.logger.info(f"获取 {index_name}({index_code}) 成分股列表")

        stock_list = data_provider.get_index_stocks(index_code)
        app.logger.info(f"找到 {len(stock_list)} 只 {index_name} 成分股")

        return jsonify({'stock_list': stock_list, 'count': len(stock_list), 'index_name': index_name})
    except Exception as e:
        app.logger.error(f"获取板块股票时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 添加到web_server.py
def clean_old_tasks():
    """清理旧的扫描任务"""
    with task_lock:
        now = datetime.now()
        to_delete = []

        for task_id, task in scan_tasks.items():
            # 解析更新时间
            try:
                updated_at = datetime.strptime(task['updated_at'], '%Y-%m-%d %H:%M:%S')
                # 如果任务完成或失败且超过1小时，或者任务状态异常且超过3小时，清理它
                if ((task['status'] in [TASK_COMPLETED, TASK_FAILED] and
                     (now - updated_at).total_seconds() > 3600) or
                        ((now - updated_at).total_seconds() > 10800)):
                    to_delete.append(task_id)
            except:
                # 日期解析错误，添加到删除列表
                to_delete.append(task_id)

        # 删除旧任务
        for task_id in to_delete:
            del scan_tasks[task_id]

        return len(to_delete)


# 修改 run_task_cleaner 函数，使其每 5 分钟运行一次并在 16:30 左右清理所有缓存
def run_task_cleaner():
    """定期运行任务清理，并在每天 16:30 左右清理所有缓存"""
    while True:
        try:
            now = datetime.now()
            # 判断是否在收盘时间附近（16:25-16:35）
            is_market_close_time = (now.hour == 16 and 25 <= now.minute <= 35)

            cleaned = clean_old_tasks()

            # 如果是收盘时间，清理所有缓存
            if is_market_close_time:
                # 清理分析器的数据缓存
                analyzer.data_cache.clear()

                # 清理 Flask 缓存
                cache.clear()

                # 清理任务存储
                with task_lock:
                    for task_type in tasks:
                        task_store = tasks[task_type]
                        completed_tasks = [task_id for task_id, task in task_store.items()
                                           if task['status'] == TASK_COMPLETED]
                        for task_id in completed_tasks:
                            del task_store[task_id]

                app.logger.info("市场收盘时间检测到，已清理所有缓存数据")

            if cleaned > 0:
                app.logger.info(f"清理了 {cleaned} 个旧的扫描任务")
        except Exception as e:
            app.logger.error(f"任务清理出错: {str(e)}")

        # 每 5 分钟运行一次，而不是每小时
        time.sleep(600)


# 基本面分析路由
@app.route('/api/fundamental_analysis', methods=['POST'])
def api_fundamental_analysis():
    try:
        data = request.json
        stock_code = data.get('stock_code')

        if not stock_code:
            return jsonify({'error': '请提供股票代码'}), 400

        # 获取基本面分析结果
        result = fundamental_analyzer.calculate_fundamental_score(stock_code)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"基本面分析出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 资金流向分析路由
# Add to web_server.py

# 获取概念资金流向的API端点
@app.route('/api/concept_fund_flow', methods=['GET'])
def api_concept_fund_flow():
    try:
        period = request.args.get('period', '10日排行')  # Default to 10-day ranking

        # Get concept fund flow data
        result = capital_flow_analyzer.get_concept_fund_flow(period)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"Error getting concept fund flow: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 获取个股资金流向排名的API端点
@app.route('/api/individual_fund_flow_rank', methods=['GET'])
def api_individual_fund_flow_rank():
    try:
        period = request.args.get('period', '10日')  # Default to today

        # Get individual fund flow ranking data
        result = capital_flow_analyzer.get_individual_fund_flow_rank(period)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"Error getting individual fund flow ranking: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 获取个股资金流向的API端点
@app.route('/api/individual_fund_flow', methods=['GET'])
def api_individual_fund_flow():
    try:
        stock_code = request.args.get('stock_code')
        market_type = request.args.get('market_type', '')  # Auto-detect if not provided
        re_date = request.args.get('period-select')

        if not stock_code:
            return jsonify({'error': 'Stock code is required'}), 400

        # Get individual fund flow data
        result = capital_flow_analyzer.get_individual_fund_flow(stock_code, market_type, re_date)
        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"Error getting individual fund flow: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 获取板块内股票的API端点
@app.route('/api/sector_stocks', methods=['GET'])
def api_sector_stocks():
    try:
        sector = request.args.get('sector')

        if not sector:
            return jsonify({'error': 'Sector name is required'}), 400

        # Get sector stocks data
        result = capital_flow_analyzer.get_sector_stocks(sector)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"Error getting sector stocks: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# Update the existing capital flow API endpoint
@app.route('/api/capital_flow', methods=['POST'])
def api_capital_flow():
    try:
        data = request.json
        stock_code = data.get('stock_code')
        market_type = data.get('market_type', '')  # Auto-detect if not provided

        if not stock_code:
            return jsonify({'error': 'Stock code is required'}), 400

        # Calculate capital flow score
        result = capital_flow_analyzer.calculate_capital_flow_score(stock_code, market_type)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"Error calculating capital flow score: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 情景预测路由
@app.route('/api/scenario_predict', methods=['POST'])
def api_scenario_predict():
    try:
        data = request.json
        stock_code = data.get('stock_code')
        market_type = data.get('market_type', 'A')
        days = data.get('days', 60)

        if not stock_code:
            return jsonify({'error': '请提供股票代码'}), 400

        # 获取情景预测结果
        result = scenario_predictor.generate_scenarios(stock_code, market_type, days)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"情景预测出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 智能问答路由
@app.route('/api/qa', methods=['POST'])
def api_qa():
    try:
        data = request.json
        stock_code = data.get('stock_code')
        question = data.get('question')
        market_type = data.get('market_type', 'A')

        if not stock_code or not question:
            return jsonify({'error': '请提供股票代码和问题'}), 400

        # 获取智能问答结果
        result = stock_qa.answer_question(stock_code, question, market_type)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"智能问答出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 风险分析路由
@app.route('/api/risk_analysis', methods=['POST'])
def api_risk_analysis():
    try:
        data = request.json
        stock_code = data.get('stock_code')
        market_type = data.get('market_type', 'A')

        if not stock_code:
            return jsonify({'error': '请提供股票代码'}), 400

        # 获取风险分析结果
        result = risk_monitor.analyze_stock_risk(stock_code, market_type)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"风险分析出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 投资组合风险分析路由
@app.route('/api/portfolio_risk', methods=['POST'])
def api_portfolio_risk():
    try:
        data = request.json
        portfolio = data.get('portfolio', [])

        if not portfolio:
            return jsonify({'error': '请提供投资组合'}), 400

        # 获取投资组合风险分析结果
        result = risk_monitor.analyze_portfolio_risk(portfolio)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"投资组合风险分析出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 指数分析路由
@app.route('/api/index_analysis', methods=['GET'])
def api_index_analysis():
    try:
        index_code = request.args.get('index_code')
        limit = int(request.args.get('limit', 30))

        if not index_code:
            return jsonify({'error': '请提供指数代码'}), 400

        # 获取指数分析结果
        result = index_industry_analyzer.analyze_index(index_code, limit)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"指数分析出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 行业分析路由
@app.route('/api/industry_analysis', methods=['GET'])
def api_industry_analysis():
    try:
        industry = request.args.get('industry')
        limit = int(request.args.get('limit', 30))

        if not industry:
            return jsonify({'error': '请提供行业名称'}), 400

        # 获取行业分析结果
        result = index_industry_analyzer.analyze_industry(industry, limit)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"行业分析出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/industry_fund_flow', methods=['GET'])
def api_industry_fund_flow():
    """获取行业资金流向数据"""
    try:
        symbol = request.args.get('symbol', '即时')

        result = industry_analyzer.get_industry_fund_flow(symbol)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"获取行业资金流向数据出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/industry_detail', methods=['GET'])
def api_industry_detail():
    """获取行业详细信息"""
    try:
        industry = request.args.get('industry')

        if not industry:
            return jsonify({'error': '请提供行业名称'}), 400

        result = industry_analyzer.get_industry_detail(industry)

        app.logger.info(f"返回前 (result)：{result}")
        if not result:
            return jsonify({'error': f'未找到行业 {industry} 的详细信息'}), 404

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"获取行业详细信息出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 行业比较路由
@app.route('/api/industry_compare', methods=['GET'])
def api_industry_compare():
    try:
        limit = int(request.args.get('limit', 10))

        # 获取行业比较结果
        result = index_industry_analyzer.compare_industries(limit)

        return custom_jsonify(result)
    except Exception as e:
        app.logger.error(f"行业比较出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 保存股票分析结果到数据库
def save_analysis_result(stock_code, market_type, result):
    """保存分析结果到数据库"""
    if not USE_DATABASE:
        return

    try:
        session = get_session()

        # 创建新的分析结果记录
        analysis = AnalysisResult(
            stock_code=stock_code,
            market_type=market_type,
            score=result.get('scores', {}).get('total', 0),
            recommendation=result.get('recommendation', {}).get('action', ''),
            technical_data=result.get('technical_analysis', {}),
            fundamental_data=result.get('fundamental_data', {}),
            capital_flow_data=result.get('capital_flow_data', {}),
            ai_analysis=result.get('ai_analysis', '')
        )

        session.add(analysis)
        session.commit()

    except Exception as e:
        app.logger.error(f"保存分析结果到数据库时出错: {str(e)}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


# 从数据库获取历史分析结果
@app.route('/api/history_analysis', methods=['GET'])
def get_history_analysis():
    """获取股票的历史分析结果"""
    if not USE_DATABASE:
        return jsonify({'error': '数据库功能未启用'}), 400

    stock_code = request.args.get('stock_code')
    limit = int(request.args.get('limit', 10))

    if not stock_code:
        return jsonify({'error': '请提供股票代码'}), 400

    try:
        session = get_session()

        # 查询历史分析结果
        results = session.query(AnalysisResult) \
            .filter(AnalysisResult.stock_code == stock_code) \
            .order_by(AnalysisResult.analysis_date.desc()) \
            .limit(limit) \
            .all()

        # 转换为字典列表
        history = [result.to_dict() for result in results]

        return jsonify({'history': history})

    except Exception as e:
        app.logger.error(f"获取历史分析结果时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()

# 添加新闻API端点
# 添加到web_server.py文件中
@app.route('/api/latest_news', methods=['GET'])
def get_latest_news():
    try:
        days = int(request.args.get('days', 1))  # 默认获取1天的新闻
        limit = int(request.args.get('limit', 1000))  # 默认最多获取1000条
        only_important = request.args.get('important', '0') == '1'  # 是否只看重要新闻
        news_type = request.args.get('type', 'all')  # 新闻类型，可选值: all, hotspot

        # 从news_fetcher模块获取新闻数据
        news_data = news_fetcher.get_latest_news(days=days, limit=limit)

        # 过滤新闻
        if only_important:
            # 根据关键词过滤重要新闻
            important_keywords = ['重要', '利好', '重磅', '突发', '关注']
            news_data = [news for news in news_data if
                         any(keyword in (news.get('content', '') or '') for keyword in important_keywords)]

        if news_type == 'hotspot':
            # 过滤舆情热点相关新闻
            hotspot_keywords = [
                # 舆情直接相关词
                '舆情', '舆论', '热点', '热议', '热搜', '话题',

                # 关注度相关词
                '关注度', '高度关注', '引发关注', '市场关注', '持续关注', '重点关注',
                '密切关注', '广泛关注', '集中关注', '投资者关注',

                # 传播相关词
                '爆文', '刷屏', '刷爆', '冲上热搜', '纷纷转发', '广泛传播',
                '热传', '病毒式传播', '迅速扩散', '高度转发',

                # 社交媒体相关词
                '微博热搜', '微博话题', '知乎热议', '抖音热门', '今日头条', '朋友圈热议',
                '微信热文', '社交媒体热议', 'APP热榜',

                # 情绪相关词
                '情绪高涨', '市场情绪', '投资情绪', '恐慌情绪', '亢奋情绪',
                '乐观情绪', '悲观情绪', '投资者情绪', '公众情绪',

                # 突发事件相关
                '突发', '紧急', '爆发', '突现', '紧急事态', '快讯', '突发事件',
                '重大事件', '意外事件', '突发新闻',

                # 行业动态相关
                '行业动向', '市场动向', '板块轮动', '资金流向', '产业趋势',
                '政策导向', '监管动态', '风口', '市场风向',

                # 舆情分析相关
                '舆情分析', '舆情监测', '舆情报告', '舆情数据', '舆情研判',
                '舆情趋势', '舆情预警', '舆情通报', '舆情简报',

                # 市场焦点相关
                '市场焦点', '焦点话题', '焦点股', '焦点事件', '投资焦点',
                '关键词', '今日看点', '重点关切', '核心议题',

                # 传统媒体相关
                '头版头条', '财经头条', '要闻', '重磅新闻', '独家报道',
                '深度报道', '特别关注', '重点报道', '专题报道',

                # 特殊提示词
                '投资舆情', '今日舆情', '今日热点', '投资热点', '市场热点',
                '每日热点', '关注要点', '交易热点', '今日重点',

                # AI基础技术
                '人工智能', 'AI', '机器学习', '深度学习', '神经网络', '大模型',
                'LLM', '大语言模型', '生成式AI', '生成式人工智能', '算法',

                # AI细分技术
                '自然语言处理', 'NLP', '计算机视觉', 'CV', '语音识别',
                '图像生成', '多模态', '强化学习', '联邦学习', '知识图谱',
                '边缘计算', '量子计算', '类脑计算', '神经形态计算',

                # 热门AI模型/产品
                'GPT', 'GPT-4', 'GPT-5', 'GPT-4o', 'ChatGPT', 'Claude',
                'Gemini', 'Llama', 'Llama3', 'Stable Diffusion', 'DALL-E',
                'Midjourney', 'Sora', 'Anthropic', 'Runway', 'Copilot',
                'Bard', 'GLM', 'Ernie', '文心一言', '通义千问', '讯飞星火','DeepSeek',

                # AI应用领域
                'AIGC', '智能驾驶', '自动驾驶', '智能助手', '智能医疗',
                '智能制造', '智能客服', '智能金融', '智能教育',
                '智能家居', '机器人', 'RPA', '数字人', '虚拟人',
                '智能安防', '计算机辅助',

                # AI硬件
                'AI芯片', 'GPU', 'TPU', 'NPU', 'FPGA', '算力', '推理芯片',
                '训练芯片', 'NVIDIA', '英伟达', 'AMD', '高性能计算',

                # AI企业
                'OpenAI', '微软AI', '谷歌AI', 'Google DeepMind', 'Meta AI',
                '百度智能云', '阿里云AI', '腾讯AI', '华为AI', '商汤科技',
                '旷视科技', '智源人工智能', '云从科技', '科大讯飞',

                # AI监管/伦理
                'AI监管', 'AI伦理', 'AI安全', 'AI风险', 'AI治理',
                'AI对齐', 'AI偏见', 'AI隐私', 'AGI', '通用人工智能',
                '超级智能', 'AI法规', 'AI责任', 'AI透明度',

                # AI市场趋势
                'AI创业', 'AI投资', 'AI融资', 'AI估值', 'AI泡沫',
                'AI风口', 'AI赛道', 'AI产业链', 'AI应用落地', 'AI转型',
                'AI红利', 'AI市值', 'AI概念股',

                # 新兴AI概念
                'AI Agent', 'AI智能体', '多智能体', '自主AI',
                'AI搜索引擎', 'RAG', '检索增强生成', '思维链', 'CoT',
                '大模型微调', '提示工程', 'Prompt Engineering',
                '基础模型', 'Foundation Model', '小模型', '专用模型',

                # 人工智能舆情专用
                'AI热点', 'AI风潮', 'AI革命', 'AI热议', 'AI突破',
                'AI进展', 'AI挑战', 'AI竞赛', 'AI战略', 'AI政策',
                'AI风险', 'AI恐慌', 'AI威胁', 'AI机遇'
            ]

            # 在API处理中使用
            if news_type == 'hotspot':
                # 过滤舆情热点相关新闻
                def has_keyword(item):
                    title = item.get('title', '')
                    content = item.get('content', '')
                    return any(keyword in title for keyword in hotspot_keywords) or \
                        any(keyword in content for keyword in hotspot_keywords)

                news_data = [news for news in news_data if has_keyword(news)]

        return jsonify({'success': True, 'news': news_data})
    except Exception as e:
        app.logger.error(f"获取最新新闻数据时出错: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/news/refresh', methods=['POST'])
def refresh_news():
    """手动触发一次新闻拉取（用于UI/排障，避免依赖定时线程）。"""
    try:
        ok = bool(news_fetcher.fetch_and_save())
        return jsonify({'success': True, 'ok': ok})
    except Exception as e:
        app.logger.error(f"刷新新闻数据时出错: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500



# --- Start of new FileSessionManager implementation ---
class FileSessionManager:
    """A Flask-compatible file-based session manager for agent tasks."""
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_task_path(self, task_id):
        return self.data_dir / f"{task_id}.json"

    def save_task(self, task_data):
        if 'id' not in task_data:
            app.logger.error("Attempted to save task without an 'id'")
            return
        task_id = task_data['id']
        task_file = self._get_task_path(task_id)
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=4, cls=NumpyJSONEncoder)

    def load_task(self, task_id):
        task_file = self._get_task_path(task_id)
        if not task_file.exists():
            return None
        with open(task_file, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                app.logger.error(f"Failed to decode JSON for task {task_id}")
                return None

    def get_all_tasks(self):
        tasks = []
        for task_file in self.data_dir.glob("*.json"):
            with open(task_file, 'r', encoding='utf-8') as f:
                try:
                    tasks.append(json.load(f))
                except json.JSONDecodeError:
                    app.logger.warning(f"Skipping corrupted task file: {task_file.name}")
                    continue
        return tasks

    def cleanup_stale_tasks(self, timeout_hours=2):
        """Clean up stale 'running' tasks that have exceeded a timeout."""
        app.logger.info("开始清理过时的任务...")
        cleaned_count = 0
        now = datetime.now()
        
        tasks = self.get_all_tasks()
        for task in tasks:
            if task.get('status') == TASK_RUNNING:
                try:
                    updated_at = datetime.strptime(task.get('updated_at'), '%Y-%m-%d %H:%M:%S')
                    if (now - updated_at).total_seconds() > timeout_hours * 3600:
                        task['status'] = TASK_FAILED
                        task['error'] = '任务因服务器重启或超时而中止'
                        task['updated_at'] = now.strftime('%Y-%m-%d %H:%M:%S')
                        self.save_task(task)
                        cleaned_count += 1
                        app.logger.warning(f"清理了过时的任务 {task.get('id')}，该任务已运行超过 {timeout_hours} 小时。")
                except (ValueError, TypeError) as e:
                    app.logger.error(f"解析任务 {task.get('id')} 的 updated_at 时出错: {e}")
                    continue
        
        if cleaned_count > 0:
            app.logger.info(f"清理完成，共处理了 {cleaned_count} 个过时的任务。")
        else:
            app.logger.info("没有发现需要清理的过时任务。")

    def delete_task(self, task_id):
        """Safely delete a task file."""
        try:
            task_file = self._get_task_path(task_id)
            if task_file.exists():
                task_file.unlink()
                return True
        except Exception as e:
            app.logger.error(f"Failed to delete task {task_id}: {e}")
        return False

# Instantiate the manager
AGENT_SESSIONS_DIR = os.path.join(os.path.dirname(__file__), '../../data/agent_sessions')
agent_session_manager = FileSessionManager(AGENT_SESSIONS_DIR)
agent_session_manager.cleanup_stale_tasks()
# --- End of new FileSessionManager implementation ---


# 智能体分析路由
@app.route('/api/start_agent_analysis', methods=['POST'])
def start_agent_analysis():
    """启动智能体分析任务"""
    try:
        data = request.json
        stock_code = data.get('stock_code')
        research_depth = data.get('research_depth', 3)
        market_type = data.get('market_type', 'A')
        selected_analysts = data.get('selected_analysts', ["market", "social", "news", "fundamentals"])
        analysis_date = data.get('analysis_date')
        enable_memory = data.get('enable_memory', True)
        max_output_length = data.get('max_output_length', 2048)

        if not stock_code:
            return jsonify({'error': '请提供股票代码'}), 400

        # 创建新任务
        task_id = generate_task_id()
        task = {
            'id': task_id,
            'status': TASK_PENDING,
            'progress': 0,
            'current_step': '任务已创建',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'params': {
                'stock_code': stock_code,
                'research_depth': research_depth,
                'market_type': market_type,
                'selected_analysts': selected_analysts,
                'analysis_date': analysis_date,
                'enable_memory': enable_memory,
                'max_output_length': max_output_length
            }
        }
        
        # 为任务创建取消事件
        task['cancel_event'] = threading.Event()
        agent_session_manager.save_task(task)
        
        def run_agent_analysis():
            """在后台线程中运行智能体分析"""
            try:
                from tradingagents.graph.trading_graph import TradingAgentsGraph
                from tradingagents.default_config import DEFAULT_CONFIG
                
                update_task_status('agent_analysis', task_id, TASK_RUNNING, progress=5, result={'current_step': '正在初始化智能体...'})

                # --- 修复 Start: 强制使用主应用的OpenAI代理配置 ---
                config = DEFAULT_CONFIG.copy()
                config['llm_provider'] = 'openai'
                config['backend_url'] = os.getenv('OPENAI_API_URL')
                main_model = os.getenv('OPENAI_API_MODEL', 'gpt-4o')
                config['deep_think_llm'] = main_model
                config['quick_think_llm'] = main_model
                config['memory_enabled'] = enable_memory
                config['max_tokens'] = max_output_length
                
                if not os.getenv('OPENAI_API_KEY'):
                    raise ValueError("主应用的 OPENAI_API_KEY 未在.env文件中设置")

                app.logger.info(f"强制使用主应用代理配置进行智能体分析: provider={config['llm_provider']}, url={config['backend_url']}, model={config['deep_think_llm']}")

                ta = TradingAgentsGraph(
                    selected_analysts=selected_analysts,
                    debug=True, 
                    config=config
                )
                # --- 修复 End ---
                
                def progress_callback(progress, step):
                    current_task = agent_session_manager.load_task(task_id)
                    if not current_task or current_task.get('status') == TASK_CANCELLED:
                         raise TaskCancelledException(f"任务 {task_id} 已被用户取消")
                    update_task_status('agent_analysis', task_id, TASK_RUNNING, progress=progress, result={'current_step': step})

                today = analysis_date or datetime.now().strftime('%Y-%m-%d')

                # Issue #34 修复: 检查propagate方法签名，兼容不同版本的tradingagents库
                import inspect
                propagate_sig = inspect.signature(ta.propagate)
                propagate_params = propagate_sig.parameters

                kwargs = {}
                if 'market_type' in propagate_params:
                    kwargs['market_type'] = market_type
                if 'progress_callback' in propagate_params:
                    kwargs['progress_callback'] = progress_callback

                # 由于tradingagents库不支持progress_callback，手动更新进度
                update_task_status('agent_analysis', task_id, TASK_RUNNING, progress=30, result={'current_step': '正在进行多智能体分析...'})
                state, raw_decision = ta.propagate(stock_code, today, **kwargs)
                update_task_status('agent_analysis', task_id, TASK_RUNNING, progress=90, result={'current_step': '正在生成分析报告...'})

                # 修复：在任务完成时，获取并添加公司名称到最终结果中
                try:
                    stock_info = analyzer.get_stock_info(stock_code)
                    stock_name = stock_info.get('股票名称', '未知')
                    if isinstance(state, dict):
                        state['company_name'] = stock_name
                except Exception as e:
                    app.logger.error(f"为 {stock_code} 获取公司名称时出错: {e}")
                    if isinstance(state, dict):
                        state['company_name'] = '名称获取失败'

                # 构造前端期望的decision对象格式
                final_trade_decision = state.get('final_trade_decision', '') if isinstance(state, dict) else ''
                action = raw_decision.strip().upper() if raw_decision else 'HOLD'
                if action not in ['BUY', 'SELL', 'HOLD']:
                    # 尝试从final_trade_decision中提取
                    if 'BUY' in final_trade_decision.upper():
                        action = 'BUY'
                    elif 'SELL' in final_trade_decision.upper():
                        action = 'SELL'
                    else:
                        action = 'HOLD'

                decision_obj = {
                    'action': action,
                    'reasoning': final_trade_decision[:500] if final_trade_decision else '分析完成',
                    'confidence': 0.7,
                    'risk_score': 0.5
                }

                update_task_status('agent_analysis', task_id, TASK_COMPLETED, progress=100, result={'decision': decision_obj, 'final_state': state, 'current_step': '分析完成'})
                app.logger.info(f"智能体分析任务 {task_id} 完成")

            except TaskCancelledException as e:
                app.logger.info(str(e))
                update_task_status('agent_analysis', task_id, TASK_FAILED, error='任务已被用户取消', result={'current_step': '任务已被用户取消'})
            except Exception as e:
                app.logger.error(f"智能体分析任务 {task_id} 失败: {str(e)}")
                app.logger.error(traceback.format_exc())
                update_task_status('agent_analysis', task_id, TASK_FAILED, error=str(e), result={'current_step': f'分析失败: {e}'})

        thread = threading.Thread(target=run_agent_analysis)
        thread.daemon = True
        thread.start()

        return jsonify({
            'task_id': task_id,
            'status': 'pending',
            'message': f'已启动对 {stock_code} 的智能体分析'
        })

    except Exception as e:
        app.logger.error(f"启动智能体分析时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agent_analysis_status/<task_id>', methods=['GET'])
def get_agent_analysis_status(task_id):
    """获取智能体分析任务的状态"""
    task = agent_session_manager.load_task(task_id)

    if not task:
        return jsonify({'error': '找不到指定的智能体分析任务'}), 404
    
    # 准备要返回的数据
    response_data = {
        'id': task['id'],
        'status': task['status'],
        'progress': task.get('progress', 0),
        'created_at': task['created_at'],
        'updated_at': task['updated_at'],
        'params': task.get('params', {})
    }
    
    if 'result' in task:
         response_data['result'] = convert_messages_to_dict(task['result'])
    if 'error' in task:
         response_data['error'] = task['error']
         
    return custom_jsonify(response_data)


@app.route('/api/agent_analysis_history', methods=['GET'])
def get_agent_analysis_history():
    """获取已完成的智能体分析任务历史"""
    try:
        all_tasks = agent_session_manager.get_all_tasks()
        history = [
            task for task in all_tasks 
            if task.get('status') in [TASK_COMPLETED, TASK_FAILED]
        ]
        # 按更新时间排序，最新的在前
        history.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        return custom_jsonify({'history': history})
    except Exception as e:
        app.logger.error(f"获取分析历史时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_agent_analysis', methods=['POST'])
def delete_agent_analysis():
    """Cancel and/or delete one or more agent analysis tasks."""
    try:
        data = request.json
        task_ids = data.get('task_ids', [])
        if not isinstance(task_ids, list):
            return jsonify({'error': 'task_ids 必须是一个列表'}), 400

        if not task_ids:
            return jsonify({'error': '请提供要删除的任务ID'}), 400

        deleted_count = 0
        cancelled_count = 0
        
        for task_id in task_ids:
            task = agent_session_manager.load_task(task_id)
            if not task:
                app.logger.warning(f"尝试删除一个不存在的任务: {task_id}")
                continue

            # If the task is running, mark it as cancelled
            if task.get('status') == TASK_RUNNING:
                task['status'] = TASK_CANCELLED
                task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                task['error'] = '任务已被用户取消'
                agent_session_manager.save_task(task)
                cancelled_count += 1
                app.logger.info(f"任务 {task_id} 已被标记为取消。")
            
            # For all other states (or after cancelling), delete the task file
            if agent_session_manager.delete_task(task_id):
                deleted_count += 1
        
        message = f"请求处理 {len(task_ids)} 个任务。已取消 {cancelled_count} 个运行中的任务，并删除了 {deleted_count} 个任务文件。"
        app.logger.info(message)
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        app.logger.error(f"删除分析历史时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/active_tasks', methods=['GET'])
def get_active_tasks():
    """获取所有正在进行的智能体分析任务"""
    try:
        all_tasks = agent_session_manager.get_all_tasks()
        active_tasks_list = []
        for task in all_tasks:
            if task.get('status') == TASK_RUNNING:
                task_info = {
                    'task_id': task['id'],
                    'stock_code': task.get('params', {}).get('stock_code'),
                    'progress': task.get('progress', 0),
                    'current_step': task.get('result', {}).get('current_step', '加载中...')
                }
                active_tasks_list.append(task_info)
        # 按创建时间排序，最新的在前
        active_tasks_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return custom_jsonify({'active_tasks': active_tasks_list})
    except Exception as e:
        app.logger.error(f"获取活动任务时出错: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# 在应用启动时启动清理线程（保持原有代码不变）
cleaner_thread = threading.Thread(target=run_task_cleaner)
cleaner_thread.daemon = True
cleaner_thread.start()

if __name__ == '__main__':
    # 强制禁用Flask的调试模式，以确保日志配置生效
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", "8888")), debug=False)
