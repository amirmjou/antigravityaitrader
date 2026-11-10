"""TradingAgents: Antigravity institutional multi-agent financial trading framework."""

from __future__ import annotations

import importlib
import sys
from importlib.abc import Loader, MetaPathFinder

__version__ = "0.7.1"

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)

from pathlib import Path
from typing import Any

# Ensure core directory is on sys.path for direct package resolution without shadowing root
_CORE_DIR = str(Path(__file__).resolve().parent)
if _CORE_DIR not in sys.path:
    sys.path.append(_CORE_DIR)

# --------------------------------------------------------------------------- #
# Dynamic Backward-Compatibility Alias for 'tradingagents' -> 'core'
# --------------------------------------------------------------------------- #
class _ModuleAliasLoader(Loader):
    def __init__(self, target: Any):
        self.target = target

    def create_module(self, spec: Any) -> Any:
        return self.target

    def exec_module(self, module: Any) -> None:
        pass


class _TradingAgentsAliasFinder(MetaPathFinder):
    """Transparently redirects legacy `tradingagents` imports to `core`."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname == "tradingagents" or fullname.startswith("tradingagents."):
            core_name = "core" + fullname[len("tradingagents"):]
            try:
                mod = importlib.import_module(core_name)
                sys.modules[fullname] = mod
                from importlib.machinery import ModuleSpec
                return ModuleSpec(fullname, _ModuleAliasLoader(mod))
            except Exception:
                return None
        return None

if not any(isinstance(f, _TradingAgentsAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _TradingAgentsAliasFinder())
sys.modules["tradingagents"] = sys.modules[__name__]

# --------------------------------------------------------------------------- #
# Primary Clean Programmatic Entry Points & Interface Contracts
# --------------------------------------------------------------------------- #
from core.agents.jev_adapter import JevAdapter, run_local_jev
from core.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    SentimentReport,
    TraderAction,
    TraderProposal,
)
from core.graph.trading_graph import TradingAgentsGraph
from core.memory import TradingMemoryLog

__all__ = [
    "JevAdapter",
    "PortfolioDecision",
    "PortfolioRating",
    "ResearchPlan",
    "SentimentReport",
    "TraderAction",
    "TraderProposal",
    "TradingAgentsGraph",
    "TradingMemoryLog",
    "__version__",
    "run_local_jev",
]
