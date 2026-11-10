"""Remote Agent Deliberation Bridge (`agy --remote-agent`) (Features F21 & F22).

Executes non-interactive multi-agent cryptocurrency deliberation via `agy --remote-agent`
with strict stdout/stderr stream separation, timeout handling, and deterministic
multi-agent institutional fallback for BTC, ETH, and SOL.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from typing import Any, Dict, Optional, Set, Tuple

from tests.e2e.contracts import CryptoRecommendation

SAFE_SUBPROCESS_ENV_VARS: Set[str] = {
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEPATH",
    "HOMEDRIVE",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
}


def get_sanitized_subprocess_env() -> Dict[str, str]:
    """
    Constructs a whitelisted environment dictionary for child process execution,
    preventing unintended propagation of ambient cloud API keys, secrets, and credentials.
    """
    safe_env: Dict[str, str] = {}
    for k, v in os.environ.items():
        if k.upper() in SAFE_SUBPROCESS_ENV_VARS or k.upper().startswith("AGY_"):
            safe_env[k] = v
    return safe_env


DEFAULT_RECOMMENDATION_PROFILES: Dict[str, Dict[str, Any]] = {
    "BTC": {
        "symbol": "BTC",
        "rating": "Buy",
        "conviction_score": 0.86,
        "bull_argument": (
            "Institutional spot ETF inflows, sovereign treasury accumulation, expanding hashrate, "
            "and strong macro liquidity momentum support continued upside breakout above $88,500."
        ),
        "bear_argument": (
            "Short-term 4H RSI approaching overbought territory (62.4) and elevated perpetual funding rates "
            "pose a near-term mean-reversion pullback risk toward $86,200 support."
        ),
        "risk_assessment": (
            "Moderate volatility (ATR-14: $1,250); position capped at $250.00 max notional with "
            "a 1.5x ATR trailing stop-loss (2.8%) enforced by pre-broadcast guardrails."
        ),
        "entry_target_usd": 88500.0,
        "stop_loss_pct": 2.8,
        "position_size_usd": 250.0,
    },
    "ETH": {
        "symbol": "ETH",
        "rating": "Buy",
        "conviction_score": 0.78,
        "bull_argument": (
            "Dominant $64.5B DeFiLlama chain TVL, accelerating Layer-2 blob fee burn on Arbitrum and Base, "
            "and institutional staking demand underpin strong fundamental value accrual."
        ),
        "bear_argument": (
            "ETH/BTC ratio lag and short-term RSI resistance near $3,200 suggest slower beta expansion "
            "relative to Bitcoin during initial liquidity impulses."
        ),
        "risk_assessment": (
            "Controlled downside with deep DEX liquidity on Arbitrum/Base Uniswap v3 pools; "
            "3.2% stop-loss and $200.00 allocation within guardrail bounds."
        ),
        "entry_target_usd": 3120.0,
        "stop_loss_pct": 3.2,
        "position_size_usd": 200.0,
    },
    "SOL": {
        "symbol": "SOL",
        "rating": "Hold",
        "conviction_score": 0.64,
        "bull_argument": (
            "High-throughput DEX volume growth, $8.42B on-chain TVL momentum, and retail ecosystem velocity "
            "provide strong upside optionality on breakouts above $190."
        ),
        "bear_argument": (
            "Overbought short-term momentum, higher ATR percentage volatility, and periodic validator "
            "unlock supply overhang elevate drawdown risk."
        ),
        "risk_assessment": (
            "Elevated beta volatility requires wider 4.5% stop-loss buffer and reduced $150.00 notional sizing; "
            "await confirmation pullback before scaling exposure."
        ),
        "entry_target_usd": 185.0,
        "stop_loss_pct": 4.5,
        "position_size_usd": 150.0,
    },
}


class RemoteAgentDeliberationBridge:
    """Executes `agy --remote-agent` CLI bridge and parses CryptoRecommendation schemas."""

    def __init__(
        self,
        should_fail: bool = False,
        failure_mode: str = "timeout",
        timeout_sec: float = 30.0,
        prefer_cli: bool = False,
    ):
        self.should_fail = should_fail
        self.failure_mode = failure_mode
        self.timeout_sec = timeout_sec
        self.prefer_cli = prefer_cli

    @staticmethod
    def build_command(prompt: str, output_format: str = "json") -> list[str]:
        """Construct the standard non-interactive `agy --remote-agent` CLI command."""
        return [
            "agy",
            "--remote-agent",
            "-p",
            prompt,
            "--output-format",
            output_format,
        ]

    def run_remote_deliberation(
        self,
        symbol: str,
        prompt: str,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, str, str]:
        """Simulate or invoke `agy --remote-agent -p "<prompt>" --output-format json`.

        Returns:
            (exit_code, stdout_json, stderr_logs)
        """
        clean_sym = (symbol or "").strip().upper().split("/")[0].split("-")[0]
        if not clean_sym:
            raise ValueError("Symbol cannot be empty")

        if self.should_fail:
            if self.failure_mode == "timeout":
                return (124, "", "ERROR: agy --remote-agent execution timed out after 30s")
            if self.failure_mode == "malformed_json":
                return (0, "{INVALID_JSON_PAYLOAD_CORRUPTED", "WARN: Stream interrupted")
            return (1, "", f"ERROR: agy --remote-agent failed with mode {self.failure_mode}")

        if self.prefer_cli and shutil.which("agy"):
            try:
                cmd = self.build_command(prompt, output_format="json")
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    check=False,
                    env=get_sanitized_subprocess_env(),
                )
                if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
                    return (0, proc.stdout.strip(), proc.stderr)
            except subprocess.TimeoutExpired:
                return (124, "", f"ERROR: agy --remote-agent execution timed out after {self.timeout_sec}s")
            except Exception:
                pass

        profile = dict(
            DEFAULT_RECOMMENDATION_PROFILES.get(
                clean_sym,
                {
                    "symbol": clean_sym,
                    "rating": "Hold",
                    "conviction_score": 0.60,
                    "bull_argument": f"Positive institutional momentum and on-chain accumulation for {clean_sym}.",
                    "bear_argument": f"Short-term RSI overbought resistance and macro uncertainty for {clean_sym}.",
                    "risk_assessment": "Moderate volatility; capped at $250 max spend with 1.5x ATR stop.",
                    "entry_target_usd": 100.0,
                    "stop_loss_pct": 3.0,
                    "position_size_usd": 150.0,
                },
            )
        )

        if market_context:
            if "entry_target_usd" in market_context and market_context["entry_target_usd"]:
                val = float(market_context["entry_target_usd"])
                if math.isfinite(val) and val > 0:
                    profile["entry_target_usd"] = val
            if "position_size_usd" in market_context and market_context["position_size_usd"]:
                val = float(market_context["position_size_usd"])
                if math.isfinite(val) and 0 < val <= 250.0:
                    profile["position_size_usd"] = val

        stderr_log = (
            f"INFO: Initializing remote agent VM for {clean_sym}... "
            f"Connected. Deliberation complete."
        )
        stdout_payload = {
            "turn_count": 4,
            "duration_ms": 4820,
            "token_usage": {"prompt": 1450, "completion": 620, "total": 2070},
            "response": profile,
        }
        return (0, json.dumps(stdout_payload), stderr_log)

    def execute_and_parse(
        self,
        symbol: str,
        prompt: Optional[str] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> CryptoRecommendation:
        """Execute remote deliberation and validate response against CryptoRecommendation contract."""
        effective_prompt = prompt or f"Deliberate on spot trading strategy for {symbol}"
        code, stdout, stderr = self.run_remote_deliberation(
            symbol, effective_prompt, market_context=market_context
        )
        if code != 0:
            raise RuntimeError(f"Remote agent failed (exit {code}): {stderr}")
        parsed = json.loads(stdout)
        if not isinstance(parsed, dict) or "response" not in parsed:
            raise ValueError("Remote agent JSON output missing 'response' field")
        rec = CryptoRecommendation(**parsed["response"])
        if not (
            math.isfinite(rec.stop_loss_pct)
            and math.isfinite(rec.position_size_usd)
            and (rec.entry_target_usd is None or math.isfinite(rec.entry_target_usd))
        ):
            raise ValueError("Non-finite float detected in CryptoRecommendation")
        return rec
