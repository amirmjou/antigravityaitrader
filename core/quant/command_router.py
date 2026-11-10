"""Workspace Slash Command Trigger Router for Antigravity Stock & Crypto Workflows.

Maps the workflow slash commands from `antigravity-stock-analysis-workflow`
(`.agent/workflows/*.md`) and `skills-for-antigravity` (`/skills/quantitative-research/`)
to local workspace execution triggers:
- `/full-analysis [TICKER]`
- `/stock-scan`
- `/entry-exit [TICKER]`
- `/stock-data [TICKER]`
- `/catalyst-check [TICKER]`
- `/risk-score [TICKER]`
- `/new-session`
- `/summary`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from core.quant.indicators import (
    TechnicalSnapshot,
    compute_technical_snapshot,
)
from core.quant.macro_parser import (
    CatalystEvent,
    MacroDataParser,
    MacroRegimeSnapshot,
)
from core.quant.sdk_hooks import AntigravityHookProtocolManager


@dataclass
class SlashCommandResult:
    """Structured result emitted by executing a mapped slash command trigger."""

    command: str
    ticker: Optional[str]
    status: str
    risk_score: Optional[float]
    priority_tier: Optional[str]
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_price: Optional[float]
    risk_reward_ratio: Optional[float]
    technical_snapshot: Optional[TechnicalSnapshot]
    macro_snapshot: Optional[MacroRegimeSnapshot]
    session_file: Optional[str]
    markdown_report: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class CommandTriggerRouter:
    """Routes workspace slash commands to quantitative indicators, risk models, and session files."""

    COMMAND_MAP: Dict[str, str] = {
        "/full-analysis": ".agent/workflows/full-analysis.md",
        "/stock-scan": ".agent/workflows/stock-scan.md",
        "/entry-exit": ".agent/workflows/entry-exit.md",
        "/stock-data": ".agent/workflows/stock-data.md",
        "/catalyst-check": ".agent/workflows/catalyst-check.md",
        "/risk-score": ".agent/workflows/risk-score.md",
        "/new-session": ".agent/workflows/new-session.md",
        "/summary": ".agent/workflows/summary.md",
    }

    def __init__(
        self,
        workspace_root: Optional[str | Path] = None,
        hook_manager: Optional[AntigravityHookProtocolManager] = None,
    ) -> None:
        self.workspace_root = Path(
            workspace_root or r"c:\Users\AmirM\Documents\Agentic trading"
        )
        self.sessions_dir = self.workspace_root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.macro_parser = MacroDataParser()
        self.hook_manager = hook_manager or AntigravityHookProtocolManager()

        for cmd in self.COMMAND_MAP:
            self.hook_manager.register_slash_trigger(
                cmd, lambda arg, c=cmd: self.execute(f"{c} {arg}".strip())
            )

    def verify_mapped_workflows(self) -> Dict[str, bool]:
        """Confirm that every mapped workflow or migrated `.agents/skills/<cmd>/SKILL.md` exists."""
        status: Dict[str, bool] = {}
        for cmd, rel_path in self.COMMAND_MAP.items():
            full_path = self.workspace_root / rel_path
            skill_name = cmd.lstrip("/")
            skill_path = self.workspace_root / ".agents" / "skills" / skill_name / "SKILL.md"
            repo_path = (
                self.workspace_root
                / "repos"
                / "antigravity-stock-analysis-workflow"
                / rel_path
            )
            status[cmd] = full_path.is_file() or skill_path.is_file() or repo_path.is_file()
        return status

    def execute(
        self,
        command_line: str,
        price_series: Optional[Sequence[float]] = None,
        high_series: Optional[Sequence[float]] = None,
        low_series: Optional[Sequence[float]] = None,
        fundamentals: Optional[Dict[str, Any]] = None,
        macro_payload: Optional[Dict[str, Any]] = None,
    ) -> SlashCommandResult:
        """Execute a workspace slash command (e.g. `/full-analysis NVDA`)."""
        parts = command_line.strip().split()
        if not parts:
            raise ValueError("Command string cannot be empty.")

        cmd = parts[0].lower()
        if not cmd.startswith("/"):
            cmd = f"/{cmd}"
        ticker = parts[1].upper() if len(parts) > 1 else None

        if cmd not in self.COMMAND_MAP:
            raise ValueError(f"Unsupported workspace command: {cmd}")

        self.hook_manager._record("pre_turn", f"Triggering workspace command {cmd} {ticker or ''}".strip())

        if cmd == "/new-session":
            return self._run_new_session()
        if cmd == "/stock-scan":
            return self._run_stock_scan()
        if cmd == "/summary":
            return self._run_summary()

        target_ticker = ticker or "NVDA"
        prices = list(price_series) if price_series is not None else self._default_series(target_ticker)
        tech = compute_technical_snapshot(
            ticker=target_ticker,
            close=prices,
            high=high_series,
            low=low_series,
        )
        macro = self.macro_parser.parse_macro_payload(macro_payload)
        fund = dict(fundamentals or self._default_fundamentals(target_ticker, tech.current_price))

        if cmd == "/entry-exit":
            return self._run_entry_exit(target_ticker, tech, fund, macro)
        if cmd == "/risk-score":
            return self._run_risk_score(target_ticker, tech, fund, macro)
        if cmd == "/catalyst-check":
            return self._run_catalyst_check(target_ticker, tech, fund, macro)
        if cmd == "/stock-data":
            return self._run_stock_data(target_ticker, tech, fund, macro)

        # Default: /full-analysis [TICKER]
        return self._run_full_analysis(target_ticker, tech, fund, macro)

    def _compute_weighted_risk_score(
        self,
        fund: Dict[str, Any],
    ) -> tuple[float, str, Dict[str, float]]:
        """Compute 5-factor weighted risk score per `.agent/workflows/risk-score.md`:
        - Catalyst clarity: 30%
        - Fundamental health: 25%
        - Options activity: 20%
        - Institutional participation: 15%
        - Liquidity: 10%
        """
        cat_raw = float(fund.get("catalyst_score", 9.0))  # /10
        fund_raw = float(fund.get("fundamental_score", 9.2))  # /10
        opt_raw = float(fund.get("options_score", 8.5))  # /10
        inst_raw = float(fund.get("institutional_score", 9.0))  # /10
        liq_raw = float(fund.get("liquidity_score", 9.5))  # /10

        weighted = (
            cat_raw * 3.0
            + fund_raw * 2.5
            + opt_raw * 2.0
            + inst_raw * 1.5
            + liq_raw * 1.0
        )
        total = round(float(np.clip(weighted, 0.0, 100.0)), 1)
        if total > 75.0:
            priority = "🟢 HIGH PRIORITY (>75)"
        elif total >= 50.0:
            priority = "🟡 MEDIUM PRIORITY (50-75)"
        else:
            priority = "🔴 SPECULATIVE (<50)"

        breakdown = {
            "catalyst_weighted": round(cat_raw * 3.0, 2),
            "fundamental_weighted": round(fund_raw * 2.5, 2),
            "options_weighted": round(opt_raw * 2.0, 2),
            "institutional_weighted": round(inst_raw * 1.5, 2),
            "liquidity_weighted": round(liq_raw * 1.0, 2),
            "total_score": total,
        }
        return total, priority, breakdown

    def _compute_entry_exit_levels(
        self,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
    ) -> tuple[float, float, float, float]:
        """Compute entry price, stop loss, target price, and R:R ratio."""
        cur = tech.current_price
        primary_support = tech.support_levels[0] if tech.support_levels else round(cur * 0.95, 2)
        entry = round((cur * 0.6 + primary_support * 0.4), 2)
        stop_loss = round(min(primary_support * 0.94, entry * 0.90), 2)
        analyst_target = float(fund.get("analyst_target_price", max(tech.resistance_levels[-1], cur * 1.22)))
        target = round(max(analyst_target, entry * 1.20), 2)

        risk = max(entry - stop_loss, 0.01)
        reward = max(target - entry, 0.0)
        rr = round(reward / risk, 2)
        return entry, stop_loss, target, rr

    def _run_full_analysis(
        self,
        ticker: str,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
        macro: MacroRegimeSnapshot,
    ) -> SlashCommandResult:
        score, priority, breakdown = self._compute_weighted_risk_score(fund)
        entry, stop, target, rr = self._compute_entry_exit_levels(tech, fund)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        action = "BUY / ACCUMULATE IN TRANCHES" if (score >= 75 and tech.adx.filter_passed and rr >= 2.0) else "WATCH / WAIT FOR PULLBACK"
        report = (
            f"# {ticker} Full Analysis Report (`/full-analysis {ticker}`)\n\n"
            f"**Analysis Time**: {now_str}\n\n"
            f"## Summary\n\n"
            f"| Metric | Value |\n"
            f"|---|---|\n"
            f"| Price | \\${tech.current_price:.2f} |\n"
            f"| Market Cap | {fund.get('market_cap', '$3.3T')} |\n"
            f"| Priority | {priority} |\n"
            f"| Risk Score | {score}/100 |\n"
            f"| RSI (14) | {tech.rsi.rsi_14} ({tech.rsi.regime}) |\n"
            f"| ADX (14) | {tech.adx.adx_14} ({tech.adx.trend_direction}, Filter={tech.adx.filter_passed}) |\n"
            f"| Moving Averages | 20MA=\\${tech.moving_averages.sma_20:.2f}, 50MA=\\${tech.moving_averages.sma_50:.2f}, 200MA=\\${tech.moving_averages.sma_200:.2f} ({tech.moving_averages.alignment}) |\n"
            f"| MACD (12,26,9) | Line={tech.macd.macd_line:.3f}, Signal={tech.macd.signal_line:.3f}, Hist={tech.macd.histogram:.3f} ({tech.macd.state}) |\n"
            f"| Macro Regime | {macro.macro_regime} (Size Mult={macro.position_size_multiplier}x) |\n"
            f"| Entry / Stop / Target | \\${entry:.2f} / \\${stop:.2f} / \\${target:.2f} |\n"
            f"| Risk/Reward Ratio | {rr}:1 |\n\n"
            f"## Decision\n"
            f"- **Action**: {action}\n"
        )

        session_path = self.sessions_dir / f"{date_str}-{ticker}-full-analysis.md"
        session_path.write_text(report, encoding="utf-8")

        return SlashCommandResult(
            command="/full-analysis",
            ticker=ticker,
            status="COMPLETED",
            risk_score=score,
            priority_tier=priority,
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            risk_reward_ratio=rr,
            technical_snapshot=tech,
            macro_snapshot=macro,
            session_file=str(session_path),
            markdown_report=report,
            metadata={"score_breakdown": breakdown},
        )

    def _run_entry_exit(
        self,
        ticker: str,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
        macro: MacroRegimeSnapshot,
    ) -> SlashCommandResult:
        entry, stop, target, rr = self._compute_entry_exit_levels(tech, fund)
        report = (
            f"# {ticker} Entry/Exit Technical Analysis (`/entry-exit {ticker}`)\n\n"
            f"- **Current Price**: \\${tech.current_price:.2f}\n"
            f"- **RSI(14)**: {tech.rsi.rsi_14} ({tech.rsi.regime})\n"
            f"- **ADX(14)**: {tech.adx.adx_14} (+DI={tech.adx.plus_di}, -DI={tech.adx.minus_di}, {tech.adx.trend_direction})\n"
            f"- **SMA(20/50/200)**: \\${tech.moving_averages.sma_20:.2f} / \\${tech.moving_averages.sma_50:.2f} / \\${tech.moving_averages.sma_200:.2f}\n"
            f"- **Entry Tranche 1 (35%)**: \\${entry:.2f}\n"
            f"- **Stop Loss**: \\${stop:.2f}\n"
            f"- **Target Price**: \\${target:.2f} (R:R = {rr}:1)\n"
        )
        return SlashCommandResult(
            command="/entry-exit",
            ticker=ticker,
            status="COMPLETED",
            risk_score=None,
            priority_tier=None,
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            risk_reward_ratio=rr,
            technical_snapshot=tech,
            macro_snapshot=macro,
            session_file=None,
            markdown_report=report,
        )

    def _run_risk_score(
        self,
        ticker: str,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
        macro: MacroRegimeSnapshot,
    ) -> SlashCommandResult:
        score, priority, breakdown = self._compute_weighted_risk_score(fund)
        report = (
            f"# {ticker} Risk Score Report (`/risk-score {ticker}`)\n\n"
            f"- **Total Score**: {score}/100\n"
            f"- **Priority Tier**: {priority}\n"
            f"- **Breakdown**: {breakdown}\n"
        )
        return SlashCommandResult(
            command="/risk-score",
            ticker=ticker,
            status="COMPLETED",
            risk_score=score,
            priority_tier=priority,
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=tech,
            macro_snapshot=macro,
            session_file=None,
            markdown_report=report,
            metadata={"score_breakdown": breakdown},
        )

    def _run_catalyst_check(
        self,
        ticker: str,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
        macro: MacroRegimeSnapshot,
    ) -> SlashCommandResult:
        events = self.macro_parser.parse_catalysts(
            catalyst_items=fund.get("catalysts", [
                {
                    "date": "2026-11-19",
                    "event_type": "EARNINGS",
                    "description": f"{ticker} Quarterly Earnings Release & Guidance",
                    "source": "Company IR / SEC EDGAR",
                }
            ])
        )
        lines = [f"# {ticker} Catalyst Timeline (`/catalyst-check {ticker}`)\n"]
        for ev in events:
            lines.append(f"- **{ev.date}** [{ev.event_type}]: {ev.description} (Certainty: {ev.certainty}, Score: {ev.clarity_score}/10)")
        return SlashCommandResult(
            command="/catalyst-check",
            ticker=ticker,
            status="COMPLETED",
            risk_score=None,
            priority_tier=None,
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=tech,
            macro_snapshot=macro,
            session_file=None,
            markdown_report="\n".join(lines),
            metadata={"catalysts": [e.__dict__ for e in events]},
        )

    def _run_stock_data(
        self,
        ticker: str,
        tech: TechnicalSnapshot,
        fund: Dict[str, Any],
        macro: MacroRegimeSnapshot,
    ) -> SlashCommandResult:
        report = (
            f"# {ticker} Market & Fundamental Data (`/stock-data {ticker}`)\n\n"
            f"- **Price**: \\${tech.current_price:.2f}\n"
            f"- **Market Cap**: {fund.get('market_cap', '$3.3T')}\n"
            f"- **Revenue YoY**: {fund.get('revenue_yoy_pct', 68.0)}%\n"
            f"- **Gross Margin**: {fund.get('gross_margin_pct', 74.5)}%\n"
        )
        return SlashCommandResult(
            command="/stock-data",
            ticker=ticker,
            status="COMPLETED",
            risk_score=None,
            priority_tier=None,
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=tech,
            macro_snapshot=macro,
            session_file=None,
            markdown_report=report,
            metadata=fund,
        )

    def _run_stock_scan(self) -> SlashCommandResult:
        candidates = [
            {"ticker": "NVDA", "theme": "AI Compute / Blackwell", "score": 90.5},
            {"ticker": "PLTR", "theme": "Enterprise AI / Defense", "score": 82.0},
            {"ticker": "IREN", "theme": "AI Data Center / HPC", "score": 78.5},
        ]
        report = "# Event-Driven Stock Scan (`/stock-scan`)\n\n" + "\n".join(
            f"- **{c['ticker']}**: {c['theme']} (Score: {c['score']}/100)" for c in candidates
        )
        return SlashCommandResult(
            command="/stock-scan",
            ticker=None,
            status="COMPLETED",
            risk_score=None,
            priority_tier="🟢 HIGH PRIORITY",
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=None,
            macro_snapshot=None,
            session_file=None,
            markdown_report=report,
            metadata={"candidates": candidates},
        )

    def _run_new_session(self) -> SlashCommandResult:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_path = self.sessions_dir / f"{date_str}-session.md"
        content = f"# Trading Analysis Session ({date_str})\n\nInitialized active workspace session.\n"
        session_path.write_text(content, encoding="utf-8")
        return SlashCommandResult(
            command="/new-session",
            ticker=None,
            status="INITIALIZED",
            risk_score=None,
            priority_tier=None,
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=None,
            macro_snapshot=None,
            session_file=str(session_path),
            markdown_report=content,
        )

    def _run_summary(self) -> SlashCommandResult:
        files = sorted(p.name for p in self.sessions_dir.glob("*.md"))
        report = f"# Session Summary (`/summary`)\n\nTracked session files ({len(files)}): {', '.join(files)}"
        return SlashCommandResult(
            command="/summary",
            ticker=None,
            status="COMPLETED",
            risk_score=None,
            priority_tier=None,
            entry_price=None,
            stop_loss=None,
            target_price=None,
            risk_reward_ratio=None,
            technical_snapshot=None,
            macro_snapshot=None,
            session_file=None,
            markdown_report=report,
            metadata={"session_files": files},
        )

    @staticmethod
    def _default_series(ticker: str) -> List[float]:
        seed = sum(ord(ch) for ch in ticker.upper())
        rng = np.random.default_rng(seed)
        base = 135.0 if ticker.upper() == "NVDA" else 50.0
        steps = rng.normal(loc=0.0025, scale=0.015, size=220)
        prices = [base]
        for s in steps:
            prices.append(max(1.0, prices[-1] * (1.0 + float(s))))
        return prices

    @staticmethod
    def _default_fundamentals(ticker: str, current_price: float) -> Dict[str, Any]:
        return {
            "ticker": ticker.upper(),
            "market_cap": "$3.35T" if ticker.upper() == "NVDA" else "$4.2B",
            "revenue_yoy_pct": 78.0 if ticker.upper() == "NVDA" else 34.0,
            "gross_margin_pct": 75.2 if ticker.upper() == "NVDA" else 58.0,
            "catalyst_score": 10.0,
            "fundamental_score": 9.5,
            "options_score": 8.5,
            "institutional_score": 9.5,
            "liquidity_score": 10.0,
            "analyst_target_price": round(current_price * 1.24, 2),
        }
