"""Unit & Integration Tests for the Quantitative Research & Workflow Ecosystem (M6).

Verifies:
- Cloned repositories in `repos/` and extracted workflows/skills in `.agent/workflows/` and `.agents/skills/`
- Quantitative formulas: Moving Averages (SMA/EMA), RSI(14), ADX(14) filter, MACD(12,26,9), IC, Walk-Forward
- Macro data & catalyst parser (`MacroDataParser`)
- Antigravity SDK Hook Protocols (`AntigravityHookProtocolManager`)
- Slash Command Trigger Router (`CommandTriggerRouter`: `/full-analysis`, `/stock-scan`, `/entry-exit`, etc.)
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from core.quant import (
    AntigravityHookProtocolManager,
    CommandTriggerRouter,
    MacroDataParser,
    analyze_walk_forward,
    calculate_information_coefficient,
    compute_adx,
    compute_ema,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    compute_sma,
    compute_technical_snapshot,
    estimate_transaction_costs,
    walk_forward_backtest,
)

WORKSPACE_ROOT = Path(r"c:\Users\AmirM\Documents\Agentic trading")


class TestClonedRepositoriesAndSkillsLayout:
    """Verify Step 1 and Step 2 repository & skill extraction."""

    def test_cloned_repositories_exist(self) -> None:
        assert (WORKSPACE_ROOT / "repos" / "antigravity-sdk-python" / "pyproject.toml").is_file()
        assert (WORKSPACE_ROOT / "repos" / "antigravity-stock-analysis-workflow" / ".agent" / "workflows" / "full-analysis.md").is_file()
        assert (WORKSPACE_ROOT / "repos" / "skills-for-antigravity" / "skills" / "quantitative-research" / "SKILL.md").is_file()

    def test_extracted_workflows_and_skills_exist(self) -> None:
        for wf in ("full-analysis", "stock-scan", "entry-exit", "risk-score", "catalyst-check", "stock-data"):
            has_workflow = (WORKSPACE_ROOT / ".agent" / "workflows" / f"{wf}.md").is_file()
            has_migrated_skill = (WORKSPACE_ROOT / ".agents" / "skills" / wf / "SKILL.md").is_file()
            assert has_workflow or has_migrated_skill

        for skill in ("quantitative-research", "algorithmic-trading", "risk-management-trading", "execution-algorithms"):
            has_agents = (WORKSPACE_ROOT / ".agents" / "skills" / skill / "SKILL.md").is_file()
            has_agent = (WORKSPACE_ROOT / ".agent" / "skills" / skill / "SKILL.md").is_file()
            assert has_agents or has_agent


class TestQuantitativeFormulas:
    """Verify SMA, EMA, RSI, ADX filter, MACD, IC, Walk-Forward, and Transaction Costs."""

    def test_moving_averages_bullish_stack(self) -> None:
        prices = [float(100 + i * 0.8) for i in range(220)]
        ma = compute_moving_averages(prices)
        assert ma.price > ma.sma_20 > ma.sma_50 > ma.sma_200
        assert ma.alignment == "BULLISH_STACK"
        assert ma.golden_cross is True

    def test_rsi_regimes(self) -> None:
        uptrend = [float(100 + i * 2.0) for i in range(40)]
        downtrend = [float(200 - i * 2.0) for i in range(40)]
        rsi_up = compute_rsi(uptrend, period=14)
        rsi_down = compute_rsi(downtrend, period=14)
        assert rsi_up.rsi_14 > 70.0
        assert rsi_up.regime == "OVERBOUGHT"
        assert rsi_down.rsi_14 < 30.0
        assert rsi_down.regime == "OVERSOLD"

    def test_adx_filter_trending_vs_ranging(self) -> None:
        close_trend = [float(100 + i * 2.5) for i in range(60)]
        high_trend = [p + 1.5 for p in close_trend]
        low_trend = [p - 0.5 for p in close_trend]
        adx_trend = compute_adx(high_trend, low_trend, close_trend, period=14)
        assert adx_trend.adx_14 >= 25.0
        assert adx_trend.is_trending is True
        assert adx_trend.filter_passed is True
        assert adx_trend.trend_direction == "BULLISH_TREND"

    def test_macd_and_technical_snapshot(self) -> None:
        prices = [float(100 + i * 0.5 + np.sin(i / 5.0)) for i in range(210)]
        macd = compute_macd(prices)
        assert isinstance(macd.macd_line, float)
        snap = compute_technical_snapshot("NVDA", prices)
        assert snap.ticker == "NVDA"
        assert len(snap.support_levels) >= 2
        assert len(snap.resistance_levels) >= 2

    def test_information_coefficient_and_walk_forward(self) -> None:
        rng = np.random.default_rng(42)
        idx = pd.date_range("2025-01-01", periods=240, freq="B")
        signal = pd.Series(rng.normal(0, 1, 240), index=idx)
        fwd_ret = signal * 0.01 + pd.Series(rng.normal(0, 0.005, 240), index=idx)
        ic_res = calculate_information_coefficient(signal, fwd_ret)
        assert ic_res["ic"] > 0.5
        assert ic_res["is_significant"] is True

        close = 100.0 * (1.0 + fwd_ret.clip(-0.05, 0.05)).cumprod()
        df = pd.DataFrame({"close": close}, index=idx)
        wf = walk_forward_backtest(
            df,
            signal_func=lambda d, p: np.sign(d["close"].pct_change(p.get("lb", 5)).fillna(0.0)),
            train_days=100,
            test_days=30,
            step_days=20,
            param_grid=[{"lb": 5}, {"lb": 10}],
        )
        assert len(wf) >= 4
        summary = analyze_walk_forward(wf)
        assert summary["total_periods"] == len(wf)

    def test_transaction_cost_model(self) -> None:
        costs = estimate_transaction_costs(
            trade_value=50_000.0,
            trade_side="buy",
            asset_class="us_equity",
            avg_daily_volume=50_000_000.0,
            volatility=0.02,
        )
        assert costs["total_cost"] > 0
        assert costs["cost_bps"] > 0


class TestMacroParserAndCommandRouter:
    """Verify MacroDataParser, AntigravityHookProtocolManager, and CommandTriggerRouter."""

    def test_macro_parser_regimes_and_catalysts(self) -> None:
        parser = MacroDataParser()
        raw = (
            "CPI YoY at 2.4%, Fed Funds at 4.25%, 10Y yield at 4.10%, VIX at 14.8\n"
            "- 2026-11-19: NVDA Q3 FY27 Earnings Release\n"
            "- 2026 Q4: DoD Sovereign AI Contract Award\n"
        )
        snap = parser.parse_macro_payload(raw_text=raw)
        assert snap.macro_regime == "RISK_ON"
        assert snap.position_size_multiplier > 1.0
        assert len(snap.catalysts) == 2
        assert snap.catalysts[0].clarity_score == 10.0
        assert snap.catalysts[1].clarity_score == 7.0

    def test_sdk_hooks_and_command_trigger_router(self) -> None:
        hooks = AntigravityHookProtocolManager()
        router = CommandTriggerRouter(workspace_root=WORKSPACE_ROOT, hook_manager=hooks)
        mapped = router.verify_mapped_workflows()
        assert all(mapped.values())

        status = hooks.inspect_protocol_status()
        assert status["sdk_installed"] is True
        assert "/full-analysis" in status["registered_slash_triggers"]
        assert "/stock-scan" in status["registered_slash_triggers"]
        assert "/entry-exit" in status["registered_slash_triggers"]

        session_res = router.execute("/new-session")
        assert session_res.status == "INITIALIZED"

        scan_res = router.execute("/stock-scan")
        assert scan_res.status == "COMPLETED"
        assert len(scan_res.metadata["candidates"]) >= 3

        ee_res = router.execute("/entry-exit NVDA")
        assert ee_res.ticker == "NVDA"
        assert ee_res.entry_price is not None
        assert ee_res.risk_reward_ratio is not None

        fa_res = router.execute("/full-analysis NVDA")
        assert fa_res.ticker == "NVDA"
        assert fa_res.risk_score is not None and fa_res.risk_score > 75.0
        assert fa_res.session_file is not None
        assert Path(fa_res.session_file).is_file()

    def test_hundred_trade_40_usd_challenge_and_ui_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from simulation.paper_trader.hundred_trade_runner import run_hundred_trade_challenge
        from visualization.server.app import create_visualization_app

        report = run_hundred_trade_challenge(initial_capital_usd=40.0, target_trades=100)
        assert report.initial_capital_usd == 40.0
        assert report.total_trades == 100
        assert report.buy_trades == 50
        assert report.sell_trades == 50
        assert report.final_equity_usd == 46.96
        assert report.net_gain_usd == 6.96

        app = create_visualization_app()
        client = TestClient(app)
        resp = client.get("/api/performance/100-trades")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_trades"] == 100
        assert payload["final_equity_usd"] == 46.96

        resp_200 = client.get("/api/performance/200-trades")
        assert resp_200.status_code == 200
        payload_200 = resp_200.json()["cumulative_200_trades"]
        assert payload_200["total_trades"] == 200
        assert payload_200["final_equity_usd"] == 64.50
        assert payload_200["cumulative_accuracy_pct"] == 63.0
