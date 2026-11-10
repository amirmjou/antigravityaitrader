"""Google Antigravity SDK Integration for Multi-Agent Trading Architecture.

Provides:
- AntigravityClient: BaseLLMClient implementation backed by Google Antigravity SDK / Gemini.
- Subagent and workflow hierarchy builders aligned with Google Antigravity SDK standards.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from core.llm_clients.base_client import BaseLLMClient
from core.llm_clients.google_client import GoogleClient, NormalizedChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

try:
    import google.antigravity as agy
    from google.antigravity import CapabilitiesConfig, LocalAgentConfig, ThinkingLevel
    ANTIGRAVITY_AVAILABLE = True
except ImportError:
    ANTIGRAVITY_AVAILABLE = False
    agy = None
    LocalAgentConfig = None
    CapabilitiesConfig = None
    ThinkingLevel = None


class AntigravityClient(BaseLLMClient):
    """LLM client bridging Google Antigravity SDK agents with LangGraph multi-agent execution."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)
        self._underlying_google_client = GoogleClient(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured LLM instance with Antigravity-aware thinking level normalization."""
        return self._underlying_google_client.get_llm()

    def validate_model(self) -> bool:
        """Validate model compatibility."""
        return self._underlying_google_client.validate_model()

    def create_antigravity_agent(
        self,
        name: str,
        system_instruction: str = "",
        thinking_level: str | None = None,
        enable_subagents: bool = False,
        max_subagent_depth: int = 2,
    ) -> Any | None:
        """Create an autonomous Google Antigravity Agent instance if SDK is present."""
        if not ANTIGRAVITY_AVAILABLE:
            logger.warning("google.antigravity SDK is not available in environment.")
            return None

        # Resolve thinking level enum if supported
        sdk_thinking = None
        if thinking_level and hasattr(agy, "ThinkingLevel"):
            level_map = {
                "high": getattr(ThinkingLevel, "HIGH", None),
                "low": getattr(ThinkingLevel, "LOW", None),
                "minimal": getattr(ThinkingLevel, "MINIMAL", None),
            }
            sdk_thinking = level_map.get(thinking_level.lower())

        config_kwargs: dict[str, Any] = {
            "model": self.model,
        }
        if sdk_thinking is not None:
            config_kwargs["thinking_level"] = sdk_thinking

        api_key = (
            self.kwargs.get("api_key")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        if api_key:
            config_kwargs["api_key"] = api_key

        capabilities = CapabilitiesConfig(
            enable_subagents=enable_subagents,
            max_subagent_depth=max_subagent_depth if enable_subagents else 0,
        )

        agent_config = LocalAgentConfig(
            capabilities=capabilities,
            **config_kwargs,
        )

        agent = agy.Agent(
            agent_config=agent_config,
            name=name,
            system_instruction=system_instruction,
        )
        return agent


def create_antigravity_trading_hierarchy(config: dict[str, Any]) -> dict[str, Any]:
    """Construct metadata representation of the 4-tier trading subagent hierarchy.

    Tiers:
    - Root: PortfolioManager (max_subagent_depth=3)
    - Mid-tier: analyst_team, research_team, risk_team, trader
    - Leaf: individual specialized agents
    """
    hierarchy = {
        "root": {
            "name": "portfolio_manager",
            "tier": "Tier 4: Portfolio Management",
            "capabilities": {"enable_subagents": True, "max_subagent_depth": 3},
            "allowed_subagents": ["risk_team", "trader"],
        },
        "trader": {
            "name": "trader",
            "tier": "Tier 3: Execution Planning",
            "capabilities": {"enable_subagents": True, "max_subagent_depth": 2},
            "allowed_subagents": ["research_team"],
        },
        "research_team": {
            "name": "research_team",
            "tier": "Tier 2: Researcher Debate",
            "allowed_subagents": ["bull_researcher", "bear_researcher", "research_manager"],
        },
        "analyst_team": {
            "name": "analyst_team",
            "tier": "Tier 1: Analysts",
            "allowed_subagents": [
                "market_analyst",
                "sentiment_analyst",
                "news_analyst",
                "fundamentals_analyst",
            ],
        },
        "risk_team": {
            "name": "risk_team",
            "tier": "Tier 4: Risk Debate",
            "allowed_subagents": [
                "aggressive_debator",
                "conservative_debator",
                "neutral_debator",
            ],
        },
    }
    return hierarchy
