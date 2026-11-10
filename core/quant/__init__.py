"""Quantitative Research, Technical Indicators, Macro Parsers, and Command Triggers.

Integrates:
1. Quantitative formulas (Moving Averages SMA/EMA, RSI, ADX filters, MACD, IC, Walk-Forward)
2. Macro data & catalyst parsers (CPI, Fed Funds, 10Y Yield, VIX, DXY, Earnings/FDA catalysts)
3. Antigravity SDK Hook Protocols (`google.antigravity.hooks`)
4. Workspace Slash Command Trigger Router (`/full-analysis`, `/stock-scan`, `/entry-exit`, etc.)
"""

from core.quant.indicators import (
    ADXResult,
    MACDResult,
    MovingAverageSnapshot,
    RSISnapshot,
    TechnicalSnapshot,
    WalkForwardResult,
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
from core.quant.macro_parser import (
    CatalystEvent,
    MacroDataParser,
    MacroRegimeSnapshot,
)
from core.quant.sdk_hooks import (
    AntigravityHookProtocolManager,
    HookEventRecord,
)
from core.quant.command_router import (
    CommandTriggerRouter,
    SlashCommandResult,
)

__all__ = [
    "ADXResult",
    "AntigravityHookProtocolManager",
    "CatalystEvent",
    "CommandTriggerRouter",
    "HookEventRecord",
    "MACDResult",
    "MacroDataParser",
    "MacroRegimeSnapshot",
    "MovingAverageSnapshot",
    "RSISnapshot",
    "SlashCommandResult",
    "TechnicalSnapshot",
    "WalkForwardResult",
    "analyze_walk_forward",
    "calculate_information_coefficient",
    "compute_adx",
    "compute_ema",
    "compute_macd",
    "compute_moving_averages",
    "compute_rsi",
    "compute_sma",
    "compute_technical_snapshot",
    "estimate_transaction_costs",
    "walk_forward_backtest",
]
