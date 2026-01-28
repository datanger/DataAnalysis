#!/usr/bin/env python3
"""
端到端验收测试脚本
测试"选股→研究→组合→模拟下单→复盘"完整闭环
"""

# This file is meant to be executed as a script, not collected by pytest.
__test__ = False

import os
import sys
import time
import json
import requests
from datetime import datetime

# 配置（优先从环境变量读取，便于一键脚本切换端口）
def _get_api_base() -> str:
    v = os.getenv("WORKBENCH_API_BASE") or os.getenv("WORKBENCH_API")
    if not v:
        host = os.getenv("WORKBENCH_HOST", "127.0.0.1")
        port = os.getenv("WORKBENCH_PORT", "8000")
        v = f"http://{host}:{port}/api/v1"

    v = v.rstrip("/")
    if not v.endswith("/api/v1"):
        v = v + "/api/v1"
    return v

WORKBENCH_API = _get_api_base()
TEST_SYMBOL = os.getenv("TEST_SYMBOL", "600519")
TEST_EXCHANGE = os.getenv("TEST_EXCHANGE", "SSE")

def log(message):
    """打印带时间戳的日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_api_get(path):
    """GET 请求封装"""
    try:
        response = requests.get(f"{WORKBENCH_API}{path}", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"[ERR] GET {path} 失败: {e}")
        return None

def test_api_post(path, data):
    """POST 请求封装"""
    try:
        response = requests.post(
            f"{WORKBENCH_API}{path}",
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"[ERR] POST {path} 失败: {e}")
        return None

def wait_for_api(max_retries=30):
    """等待API服务启动"""
    log("Waiting for API service...")
    for i in range(max_retries):
        try:
            response = requests.get(f"{WORKBENCH_API}/health", timeout=5)
            if response.status_code == 200:
                log("[OK] API service ready")
                return True
        except:
            pass
        time.sleep(2)
    log("API Service Timeout")
    return False

def test_1_health():
    """测试1: 健康检查"""
    log("\nTest:1: 健康检查 ===")
    result = test_api_get("/health")
    if result and result.get("ok"):
        log("[OK] health")
        return True
    log("[ERR] health")
    return False

def test_2_ingest_instruments():
    """测试2: 摄取标的清单"""
    log("\nTest:2: 摄取标的清单 ===")
    result = test_api_post("/tasks/run", {
        "type": "ingest_instruments",
        "payload": {}
    })
    if result and result.get("ok"):
        task_id = result["data"]["task_id"]
        log(f"[OK] 摄取任务已启动，任务ID: {task_id}")

        # 等待任务完成
        for i in range(15):
            time.sleep(2)
            status = test_api_get(f"/tasks/{task_id}")
            if status and status["data"]["status"] in ["COMPLETED", "SUCCESS"]:
                log("[OK] 摄取完成")
                return True
            log(f"Waiting for task... ({i+1}/15)")
        log("WARNING  摄取任务超时")
    else:
        log("[ERR] 摄取任务启动失败")
    return False

def test_3_ingest_bars():
    """测试3: 摄取K线数据"""
    log("\nTest:3: 摄取K线数据 ===")
    result = test_api_post("/tasks/run", {
        "type": "ingest_bars_daily",
        "payload": {
            "symbols": [{"symbol": TEST_SYMBOL, "exchange": TEST_EXCHANGE}],
            "start_date": "20240101"
        }
    })
    if result and result.get("ok"):
        task_id = result["data"]["task_id"]
        log(f"[OK] K线摄取任务已启动，任务ID: {task_id}")

        # 等待任务完成
        for i in range(15):
            time.sleep(2)
            status = test_api_get(f"/tasks/{task_id}")
            if status and status["data"]["status"] in ["COMPLETED", "SUCCESS"]:
                log("[OK] K线摄取完成")
                return True
            log(f"Waiting for task... ({i+1}/15)")
        log("WARNING  K线摄取任务超时")
    else:
        log("[ERR] K线摄取任务启动失败")
    return False

def test_4_workspace():
    """测试4: 个股工作台"""
    log("\nTest:4: 个股工作台 ===")
    result = test_api_get(f"/stocks/{TEST_EXCHANGE}/{TEST_SYMBOL}/workspace")
    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 工作台数据获取成功")
        log(f"   - K线数据: {len(data.get('price_bars', []))} 条")
        log(f"   - 技术指标: {len(data.get('indicators', []))} 条")
        log(f"   - 最新评分: {data.get('latest_score', {}).get('score_total', 'N/A')}")
        return True
    log("[ERR] 工作台数据获取失败")
    return False

def test_5_scores():
    """测试5: 评分计算"""
    log("\nTest:5: 评分计算 ===")
    result = test_api_post("/scores/calc", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE
    })
    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 评分计算成功")
        log(f"   - 总分: {data.get('score_total', 'N/A')}")
        log(f"   - 分项: {data.get('breakdown_json', {})}")
        log(f"   - 原因: {data.get('reasons_json', [])}")
        return True
    log("[ERR] 评分计算失败")
    return False

def test_6_plans():
    """测试6: 计划生成"""
    log("\nTest:6: 计划生成 ===")
    result = test_api_post("/plans/generate", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE
    })
    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 计划生成成功")
        log(f"   - 计划ID: {data.get('plan_id', 'N/A')}")
        log(f"   - 版本: {data.get('plan_version', 'N/A')}")
        log(f"   - 方向: {data.get('plan_json', {}).get('direction', 'N/A')}")
        return True
    log("[ERR] 计划生成失败")
    return False

def test_7_notes():
    """测试7: 研究纪要"""
    log("\nTest:7: 研究纪要 ===")
    result = test_api_post("/notes", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "content_md": f"# {TEST_SYMBOL} 研究纪要\n\n测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n- 基本面：暂无\n- 技术面：暂无\n- 资金面：暂无\n"
    })
    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 纪要创建成功")
        log(f"   - 纪要ID: {data.get('note_id', 'N/A')}")
        return True
    log("[ERR] 纪要创建失败")
    return False

def test_8_portfolio():
    """测试8: 组合管理"""
    log("\nTest:8: 组合管理 ===")
    # 创建组合
    result = test_api_post("/portfolios", {
        "name": "测试组合",
        "initial_cash": 1000000
    })
    if not result or not result.get("ok"):
        log("[ERR] 组合创建失败")
        return False

    portfolio_id = result["data"]["portfolio_id"]
    log(f"[OK] 组合创建成功，ID: {portfolio_id}")

    # 获取组合
    result = test_api_get(f"/portfolios/{portfolio_id}")
    if result and result.get("ok"):
        log("[OK] 组合查询成功")
        log(f"   - 名称: {result['data']['name']}")
        log(f"   - 现金: {result['data']['cash']}")
        return True
    log("[ERR] 组合查询失败")
    return False

def test_9_rebalance():
    """测试9: 调仓建议"""
    log("\nTest:9: 调仓建议 ===")

    # 先创建组合
    portfolio_result = test_api_post("/portfolios", {
        "name": "调仓测试组合",
        "initial_cash": 1000000
    })
    if not portfolio_result or not portfolio_result.get("ok"):
        log("[ERR] 组合创建失败")
        return False

    portfolio_id = portfolio_result["data"]["portfolio_id"]

    # 生成调仓建议
    result = test_api_post("/rebalance/suggest", {
        "portfolio_id": portfolio_id,
        "targets": [
            {"symbol": TEST_SYMBOL, "exchange": TEST_EXCHANGE, "weight": 1.0}
        ],
        "cash_reserve_ratio": 0.1,
        "create_drafts": True
    })

    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 调仓建议生成成功")
        log(f"   - 建议订单: {len(data.get('suggestions', []))} 个")
        log(f"   - 草稿: {len(data.get('drafts', []))} 个")
        return True
    log("[ERR] 调仓建议生成失败")
    return False

def test_10_risk_check():
    """测试10: 风控校验"""
    log("\nTest:10: 风控校验 ===")

    # 先创建组合和草稿
    portfolio_result = test_api_post("/portfolios", {
        "name": "风控测试组合",
        "initial_cash": 1000000
    })
    if not portfolio_result or not portfolio_result.get("ok"):
        log("[ERR] 组合创建失败")
        return False

    portfolio_id = portfolio_result["data"]["portfolio_id"]

    # 创建草稿
    draft_result = test_api_post("/order_drafts", {
        "portfolio_id": portfolio_id,
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "side": "BUY",
        "order_type": "LIMIT",
        "qty": 100,
        "price": 1800.0
    })
    if not draft_result or not draft_result.get("ok"):
        log("[ERR] 草稿创建失败")
        return False

    draft_id = draft_result["data"]["draft_id"]

    # 风控校验
    result = test_api_post("/risk/check", {
        "draft_ids": [draft_id]
    })

    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 风控校验完成")
        log(f"   - 状态: {data.get('status', 'N/A')}")
        log(f"   - 项目数: {len(data.get('items_json', []))}")
        return True
    log("[ERR] 风控校验失败")
    return False

def test_11_sim_trade():
    """测试11: 模拟交易"""
    log("\nTest:11: 模拟交易 ===")

    # 先创建组合和草稿
    portfolio_result = test_api_post("/portfolios", {
        "name": "模拟交易组合",
        "initial_cash": 1000000
    })
    if not portfolio_result or not portfolio_result.get("ok"):
        log("[ERR] 组合创建失败")
        return False

    portfolio_id = portfolio_result["data"]["portfolio_id"]

    # 创建草稿
    draft_result = test_api_post("/order_drafts", {
        "portfolio_id": portfolio_id,
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "side": "BUY",
        "order_type": "LIMIT",
        "qty": 100,
        "price": 1800.0
    })
    if not draft_result or not draft_result.get("ok"):
        log("[ERR] 草稿创建失败")
        return False

    draft_id = draft_result["data"]["draft_id"]

    # 风控校验
    risk_result = test_api_post("/risk/check", {
        "draft_ids": [draft_id]
    })
    if not risk_result or not risk_result.get("ok"):
        log("[ERR] 风控校验失败")
        return False

    riskcheck_id = risk_result["data"]["riskcheck_id"]

    # 确认模拟交易
    result = test_api_post("/sim/confirm", {
        "draft_ids": [draft_id],
        "riskcheck_id": riskcheck_id
    })

    if result and result.get("ok"):
        data = result["data"]
        log("[OK] 模拟交易确认成功")
        log(f"   - 订单: {len(data.get('orders', []))} 个")
        log(f"   - 成交: {len(data.get('trades', []))} 个")

        # 验证台账
        orders = test_api_get(f"/sim/orders?portfolio_id={portfolio_id}")
        trades = test_api_get(f"/sim/trades?portfolio_id={portfolio_id}")

        if orders and trades:
            log("[OK] 台账查询成功")
            log(f"   - 订单记录: {len(orders['data'])} 条")
            log(f"   - 成交记录: {len(trades['data'])} 条")
        return True
    log("[ERR] 模拟交易确认失败")
    return False

def main():
    """主测试流程"""
    log("开始端到端验收测试")
    log(f"测试标的: {TEST_SYMBOL} ({TEST_EXCHANGE})")
    log(f"API 地址: {WORKBENCH_API}")

    # 等待API启动
    if not wait_for_api():
        sys.exit(1)

    # 执行测试
    tests = [
        ("健康检查", test_1_health),
        ("摄取标的", test_2_ingest_instruments),
        ("摄取K线", test_3_ingest_bars),
        ("工作台", test_4_workspace),
        ("评分", test_5_scores),
        ("计划", test_6_plans),
        ("纪要", test_7_notes),
        ("组合", test_8_portfolio),
        ("调仓", test_9_rebalance),
        ("风控", test_10_risk_check),
        ("模拟交易", test_11_sim_trade),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            log(f"[ERR] 测试异常: {name} - {e}")
            results.append((name, False))

    # 汇总结果
    log("\n" + "="*50)
    log("测试结果汇总")
    log("="*50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        log(f"{status} {name}")

    log("="*50)
    log(f"Summary: {passed}/{total} 通过")
    log(f"Pass Rate: {passed/total*100:.1f}%")
    log("="*50)

    if passed == total:
        log("[OK] 所有测试通过！系统验收成功")
        sys.exit(0)
    else:
        log("WARNING  部分测试失败，请检查系统")
        sys.exit(1)

if __name__ == "__main__":
    main()
