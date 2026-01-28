#!/usr/bin/env python3
"""Quick end-to-end test for the workbench system"""

# This file is meant to be executed as a script, not collected by pytest.
__test__ = False

import os
import sys
import time
import json
import requests
from datetime import datetime

# Configuration
WORKBENCH_API = "http://127.0.0.1:8001/api/v1"
TEST_SYMBOL = "600519"
TEST_EXCHANGE = "SSE"

def log(message):
    """Print log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_api_get(path):
    """GET request wrapper"""
    try:
        response = requests.get(f"{WORKBENCH_API}{path}", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"ERROR GET {path}: {e}")
        return None

def test_api_post(path, data):
    """POST request wrapper"""
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
        log(f"ERROR POST {path}: {e}")
        return None

def test_1_health():
    """Test 1: Health check"""
    log("\n=== Test 1: Health Check ===")
    result = test_api_get("/health")
    if result and result.get("ok"):
        log("PASS Health check")
        return True
    log("FAIL Health check")
    return False

def test_2_workspace():
    """Test 2: Stock workspace"""
    log("\n=== Test 2: Stock Workspace ===")
    result = test_api_get(f"/stocks/{TEST_EXCHANGE}/{TEST_SYMBOL}/workspace")
    if result and result.get("ok"):
        data = result["data"]
        log(f"PASS Workspace data retrieved")
        log(f"   - K-line data: {len(data.get('price_bars', []))} records")
        log(f"   - Indicators: {len(data.get('indicators', []))} records")
        return True
    log("FAIL Workspace data retrieval")
    return False

def test_3_scores():
    """Test 3: Score calculation"""
    log("\n=== Test 3: Score Calculation ===")
    result = test_api_post("/scores/calc", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE
    })
    if result and result.get("ok"):
        data = result["data"]
        log(f"PASS Score calculation")
        log(f"   - Total score: {data.get('score_total', 'N/A')}")
        return True
    log("FAIL Score calculation")
    return False

def test_4_plans():
    """Test 4: Plan generation"""
    log("\n=== Test 4: Plan Generation ===")
    result = test_api_post("/plans/generate", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE
    })
    if result and result.get("ok"):
        data = result["data"]
        log(f"PASS Plan generation")
        log(f"   - Plan ID: {data.get('plan_id', 'N/A')}")
        return True
    log("FAIL Plan generation")
    return False

def test_5_notes():
    """Test 5: Research notes"""
    log("\n=== Test 5: Research Notes ===")
    result = test_api_post("/notes", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "content_md": f"# {TEST_SYMBOL} Research Notes\n\nTest time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    })
    if result and result.get("ok"):
        data = result["data"]
        log(f"PASS Note creation")
        log(f"   - Note ID: {data.get('note_id', 'N/A')}")
        return True
    log("FAIL Note creation")
    return False

def test_6_portfolio():
    """Test 6: Portfolio management"""
    log("\n=== Test 6: Portfolio Management ===")
    result = test_api_post("/portfolios", {
        "name": "Test Portfolio",
        "initial_cash": 1000000
    })
    if result and result.get("ok"):
        portfolio_id = result["data"]["portfolio_id"]
        log(f"PASS Portfolio creation, ID: {portfolio_id}")
        return True
    log("FAIL Portfolio creation")
    return False

def test_7_news():
    """Test 7: News ingestion"""
    log("\n=== Test 7: News ===")
    result = test_api_post("/news/ingest_mock", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "count": 5
    })
    if result and result.get("ok"):
        log(f"PASS News ingestion")
        return True
    log("FAIL News ingestion")
    return False

def test_8_risk_rules():
    """Test 8: Risk rules"""
    log("\n=== Test 8: Risk Rules ===")
    result = test_api_get("/risk/rules")
    if result and result.get("ok"):
        rules = result.get("data", {})
        log(f"PASS Risk rules retrieved, count: {len(rules)}")
        return True
    log("FAIL Risk rules retrieval")
    return False

def test_9_reports():
    """Test 9: Report generation"""
    log("\n=== Test 9: Report Generation ===")
    result = test_api_post("/reports/stock", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "report_type": "comprehensive"
    })
    if result and result.get("ok"):
        log(f"PASS Report generation")
        return True
    log("FAIL Report generation")
    return False

def test_10_monitor():
    """Test 10: Monitor rules"""
    log("\n=== Test 10: Monitor ===")
    result = test_api_post("/monitor/rules", {
        "symbol": TEST_SYMBOL,
        "exchange": TEST_EXCHANGE,
        "rule_type": "price_change_pct",
        "threshold": 5.0,
        "condition": "above"
    })
    if result and result.get("ok"):
        log(f"PASS Monitor rule creation")
        return True
    log("FAIL Monitor rule creation")
    return False

def main():
    """Main test flow"""
    log("="*50)
    log("Starting End-to-End Test")
    log("="*50)
    log(f"Test Symbol: {TEST_SYMBOL} ({TEST_EXCHANGE})")
    log(f"API Address: {WORKBENCH_API}")

    # Wait for API to be ready
    log("\nWaiting for API service...")
    for i in range(10):
        try:
            response = requests.get(f"{WORKBENCH_API}/health", timeout=5)
            if response.status_code == 200:
                log("API service is ready")
                break
        except:
            pass
        time.sleep(2)
        log(f"Waiting... ({i+1}/10)")
    else:
        log("ERROR: API service timeout")
        sys.exit(1)

    # Run tests
    tests = [
        ("Health", test_1_health),
        ("Workspace", test_2_workspace),
        ("Scores", test_3_scores),
        ("Plans", test_4_plans),
        ("Notes", test_5_notes),
        ("Portfolio", test_6_portfolio),
        ("News", test_7_news),
        ("Risk Rules", test_8_risk_rules),
        ("Reports", test_9_reports),
        ("Monitor", test_10_monitor),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            log(f"ERROR Test exception: {name} - {e}")
            results.append((name, False))

    # Summary
    log("\n" + "="*50)
    log("Test Results Summary")
    log("="*50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        log(f"{status} {name}")

    log("="*50)
    log(f"Total: {passed}/{total} passed")
    log(f"Pass Rate: {passed/total*100:.1f}%")
    log("="*50)

    if passed == total:
        log("SUCCESS: All tests passed!")
        sys.exit(0)
    else:
        log("WARNING: Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
