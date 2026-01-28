#!/usr/bin/env python3
"""Test backtest functionality"""

# This file is meant to be executed as a script, not collected by pytest.
__test__ = False

import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, '/d/Work/Git/DataAnalysis')

from workbench.db.conn import connect
from workbench.services.backtest import BacktestService

def test_backtest_basic():
    """Test basic backtest functionality."""
    print("=" * 60)
    print("Testing Backtest Service")
    print("=" * 60)

    # Connect to database
    db_path = "/d/Work/Git/DataAnalysis/data/workbench.db"
    conn = connect(db_path)

    try:
        backtest = BacktestService(conn)

        # Test parameters
        symbol = "600519"
        exchange = "SSE"
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        initial_cash = 1000000

        print(f"\nTest Parameters:")
        print(f"  Symbol: {symbol}")
        print(f"  Exchange: {exchange}")
        print(f"  Period: {start_date} to {end_date}")
        print(f"  Initial Cash: {initial_cash:,}")

        # Run backtest
        print(f"\nRunning backtest...")
        result = backtest.run_backtest(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            signal_type="score_threshold",
            signal_params={
                "threshold": 70,
                "position_size": 0.5,
                "stop_loss": 0.1,
                "take_profit": 0.2,
            }
        )

        print(f"\n{'='*60}")
        print("BACKTEST RESULTS")
        print(f"{'='*60}")

        # Print metrics
        metrics = result["metrics"]
        print(f"\nPerformance Metrics:")
        print(f"  Total Return: {metrics['total_return_pct']:.2f}%")
        print(f"  Annualized Return: {metrics['annualized_return_pct']:.2f}%")
        print(f"  Annualized Volatility: {metrics['annualized_volatility_pct']:.2f}%")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"  Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  CAGR: {metrics['cagr_pct']:.2f}%")

        # Print trades summary
        trades = result["trades"]
        print(f"\nTrades Summary:")
        print(f"  Total Trades: {len(trades)}")

        if trades:
            entry_trades = [t for t in trades if t["side"] == "BUY"]
            exit_trades = [t for t in trades if t["side"] == "SELL"]
            print(f"  Entry Trades: {len(entry_trades)}")
            print(f"  Exit Trades: {len(exit_trades)}")

        # Print equity curve summary
        equity_curve = result["equity_curve"]
        print(f"\nEquity Curve:")
        print(f"  Data Points: {len(equity_curve)}")
        if equity_curve:
            print(f"  Initial Value: {equity_curve[0]['total_value']:,.2f}")
            print(f"  Final Value: {equity_curve[-1]['total_value']:,.2f}")

        print(f"\n{'='*60}")
        print("Test PASSED!")
        print(f"{'='*60}")

        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()


def test_backtest_compare():
    """Test strategy comparison."""
    print("\n" + "=" * 60)
    print("Testing Strategy Comparison")
    print("=" * 60)

    db_path = "/d/Work/Git/DataAnalysis/data/workbench.db"
    conn = connect(db_path)

    try:
        backtest = BacktestService(conn)

        symbol = "600519"
        exchange = "SSE"
        start_date = "2024-01-01"
        end_date = "2024-12-31"

        strategies = [
            {
                "name": "High Threshold",
                "signal_type": "score_threshold",
                "signal_params": {"threshold": 80, "position_size": 0.5}
            },
            {
                "name": "Low Threshold",
                "signal_type": "score_threshold",
                "signal_params": {"threshold": 60, "position_size": 0.5}
            },
            {
                "name": "Conservative",
                "signal_type": "score_threshold",
                "signal_params": {"threshold": 75, "position_size": 0.3}
            }
        ]

        print(f"\nComparing {len(strategies)} strategies...")

        result = backtest.compare_strategies(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            strategies=strategies
        )

        print(f"\n{'='*60}")
        print("STRATEGY COMPARISON")
        print(f"{'='*60}")

        for strategy in result["strategies"]:
            metrics = strategy["metrics"]
            print(f"\n{strategy['strategy_name']}:")
            print(f"  Total Return: {metrics['total_return_pct']:.2f}%")
            print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
            print(f"  Trades: {strategy['trade_count']}")

        print(f"\n{'='*60}")
        print(f"Best by Return: {result['best_by_return']['name']} ({result['best_by_return']['total_return_pct']:.2f}%)")
        print(f"Best by Sharpe: {result['best_by_sharpe']['name']} ({result['best_by_sharpe']['sharpe_ratio']:.2f})")
        print(f"{'='*60}")

        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    # Run tests
    test1_passed = test_backtest_basic()
    test2_passed = test_backtest_compare()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Test 1 (Basic Backtest): {'PASS' if test1_passed else 'FAIL'}")
    print(f"Test 2 (Strategy Comparison): {'PASS' if test2_passed else 'FAIL'}")
    print("=" * 60)

    if test1_passed and test2_passed:
        print("\nAll tests PASSED!")
        sys.exit(0)
    else:
        print("\nSome tests FAILED!")
        sys.exit(1)
