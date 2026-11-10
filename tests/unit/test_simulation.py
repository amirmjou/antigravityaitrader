"""Unit Test Suite for Paper Trading & Multi-Asset Backtester (Milestone 5 — F24–F26)."""
from __future__ import annotations

import pytest

from simulation import MultiAssetBacktestGridRunner, PaperTradingEngine
from tests.e2e.contracts import BacktestResultSummary


class TestPaperTradingEngineUnit:
    def test_buy_and_sell_lifecycle_with_pnl(self):
        engine = PaperTradingEngine(initial_cash_usd=10000.0)
        buy1 = engine.place_order("ETH/USDT", "Buy", 1.0, 3000.0)
        buy2 = engine.place_order("ETH/USDT", "Buy", 1.0, 3200.0)
        assert buy1.status == "filled"
        assert buy2.status == "filled"
        assert engine.cash_usd == pytest.approx(3800.0)
        pos = engine.positions["ETH/USDT"]
        assert pos.quantity == pytest.approx(2.0)
        assert pos.average_entry_price == pytest.approx(3100.0)

        # Mark to market at 3300
        unrealized = engine.mark_to_market("ETH/USDT", 3300.0)
        assert unrealized == pytest.approx(400.0)
        assert engine.total_portfolio_value_usd() == pytest.approx(10400.0)

        # Sell 1 ETH at 3400 -> realized PnL = (3400 - 3100) * 1 = +300
        sell1 = engine.place_order("ETH/USDT", "Sell", 1.0, 3400.0)
        assert sell1.status == "filled"
        assert pos.quantity == pytest.approx(1.0)
        assert pos.realized_pnl_usd == pytest.approx(300.0)
        assert engine.cash_usd == pytest.approx(7200.0)

    def test_rejects_negative_zero_or_insufficient_cash(self):
        engine = PaperTradingEngine(initial_cash_usd=1000.0)
        neg_order = engine.place_order("BTC/USDT", "Buy", -0.5, 88500.0)
        assert neg_order.status == "rejected"
        assert engine.cash_usd == 1000.0

        zero_order = engine.place_order("BTC/USDT", "Buy", 0.0, 88500.0)
        assert zero_order.status == "rejected"

        over_budget = engine.place_order("BTC/USDT", "Buy", 1.0, 88500.0)
        assert over_budget.status == "rejected"
        assert engine.cash_usd == 1000.0

        short_sell = engine.place_order("SOL/USDT", "Sell", 1.0, 185.0)
        assert short_sell.status == "rejected"


class TestMultiAssetBacktestGridRunner:
    def test_backtest_grid_across_btc_eth_sol(self):
        runner = MultiAssetBacktestGridRunner(initial_cash_usd=10000.0)
        grid = runner.run_grid(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
        assert set(grid.keys()) == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
        for sym, summary in grid.items():
            assert isinstance(summary, BacktestResultSummary)
            assert summary.ticker == sym
            assert summary.total_trades > 0
            assert summary.winning_trades + summary.losing_trades == summary.total_trades
            assert 0.0 <= summary.win_rate_pct <= 100.0
