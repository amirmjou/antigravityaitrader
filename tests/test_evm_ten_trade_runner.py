"""Unit tests for the Real-World 10-Trade $2.00 ETH Execution & Accuracy Simulator."""
from __future__ import annotations

from simulation.paper_trader.evm_ten_trade_runner import (
    run_ten_trade_2usd_eth_simulation,
)


def test_ten_trade_2usd_eth_simulation_invariants() -> None:
    report = run_ten_trade_2usd_eth_simulation(initial_usd=2.00, eth_price_usd=3120.0)

    assert report.initial_usd == 2.00
    assert report.total_executed_trades == 10
    assert len(report.trades) == 10
    assert report.intercepted_bad_alerts == 4
    assert report.guardrail_interception_accuracy_pct == 100.0

    # Verify sequential nonces 0..19 with zero gaps or collisions
    expected_nonce = 0
    for trade in report.trades:
        assert trade.entry_nonce == expected_nonce
        assert trade.exit_nonce == expected_nonce + 1
        expected_nonce += 2
        # Slippage must strictly adhere to trader-validation-pipeline <= 15 bps (0.15%)
        assert trade.slippage_bps <= 15
        # RSI at entry must strictly be below macro overbought threshold (< 70.0)
        assert trade.rsi_entry < 70.0
        # Every trade must have passed pre-flight eth_call simulation
        assert trade.eth_call_simulated is True

    # Verify EIP-1559 stuck-nonce speed-up was tested on Trade #4
    trade_4 = report.trades[3]
    assert trade_4.speed_up_applied is True
    assert trade_4.speed_up_fee_bump_pct == 15.0
    assert report.stuck_nonce_recoveries == 1

    # Verify accuracy and positive net return after all real-world L2 gas + DEX + slippage fees
    assert report.winning_trades == 8
    assert report.losing_trades == 2
    assert report.trade_win_rate_pct == 80.0
    assert report.overall_decision_accuracy_pct == 85.7
    assert report.final_wallet_usd > report.initial_usd
    assert report.total_l2_gas_paid_usd > 0.0
    assert report.total_dex_and_slippage_paid_usd > 0.0
