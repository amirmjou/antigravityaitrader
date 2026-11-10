"""LangChain & LangGraph callback handler streaming reasoning tokens and tool calls."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
try:
    from langchain_core.callbacks.base import BaseCallbackHandler
except ImportError:
    class BaseCallbackHandler:  # type: ignore
        pass

from visualization.telemetry.hub import TelemetryHub

logger = logging.getLogger(__name__)


class ReasoningStreamCallbackHandler(BaseCallbackHandler):
    """Callback handler capturing token-by-token LLM generation and tool telemetry."""

    def __init__(self, hub: TelemetryHub, default_role: str = "Market Analyst"):
        super().__init__()
        self.hub = hub
        self.current_role = default_role
        self.debate_round = 1

    def set_active_agent(self, role: str, round_num: int = 1) -> None:
        """Sets the active agent role and debate round for subsequent token emissions."""
        self.current_role = role
        self.debate_round = round_num

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Emitted token-by-token as LLM reasons or outputs text."""
        if not token:
            return
        self.hub.publish_event(
            event_type="agent_thought",
            role=self.current_role,
            token=token,
            debate_round=self.debate_round,
        )

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Emitted when an agent invokes a tool (e.g. CCXT ticker fetch)."""
        tool_name = serialized.get("name", "tool") if isinstance(serialized, dict) else str(serialized)
        self.hub.publish_event(
            event_type="tool_call",
            role=self.current_role,
            token=f"{tool_name}({input_str})",
            snapshot={"tool": tool_name, "input": input_str},
            debate_round=self.debate_round,
        )

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        """Emitted when tool returns result."""
        out_summary = output if isinstance(output, dict) else str(output)
        self.hub.publish_event(
            event_type="tool_call",
            role=self.current_role,
            token=f"Result: {str(out_summary)[:120]}",
            snapshot={"output": out_summary},
            debate_round=self.debate_round,
        )

    def publish_debate_argument(self, role: str, argument: str, round_num: int = 1) -> None:
        """Publish full debate argument from Bull or Bear researcher."""
        self.hub.publish_event(
            event_type="debate_argument",
            role=role,
            token=argument,
            debate_round=round_num,
        )

    def publish_debate_turn(self, role: str, argument: str, round_num: int = 1) -> None:
        """Publish debate turn transition."""
        self.hub.publish_event(
            event_type="debate_turn",
            role=role,
            token=argument,
            debate_round=round_num,
        )

    def publish_proposal(self, role: str, proposal: Dict[str, Any] | Any) -> None:
        """Publish TraderProposal telemetry."""
        snapshot = proposal if isinstance(proposal, dict) else (proposal.model_dump() if hasattr(proposal, "model_dump") else str(proposal))
        token_str = f"Proposal generated: {snapshot.get('action', 'TRADE')} on {snapshot.get('symbol', 'UNKNOWN')}" if isinstance(snapshot, dict) else str(snapshot)
        self.hub.publish_event(
            event_type="proposal_generated",
            role=role,
            token=token_str,
            snapshot=snapshot if isinstance(snapshot, dict) else {"proposal": snapshot},
            consensus_status="proposed",
        )

    def publish_decision(self, role: str, decision: Dict[str, Any] | Any) -> None:
        """Publish PortfolioDecision telemetry."""
        snapshot = decision if isinstance(decision, dict) else (decision.model_dump() if hasattr(decision, "model_dump") else str(decision))
        token_str = f"Decision ratified: {snapshot.get('rating', 'HOLD')}" if isinstance(snapshot, dict) else str(snapshot)
        self.hub.publish_event(
            event_type="decision",
            role=role,
            token=token_str,
            snapshot=snapshot if isinstance(snapshot, dict) else {"decision": snapshot},
            consensus_status="approved",
        )

    def publish_trade_execution(self, role: str, tx_info: Dict[str, Any] | Any) -> None:
        """Publish on-chain or paper trade execution telemetry."""
        snapshot = tx_info if isinstance(tx_info, dict) else (tx_info.model_dump() if hasattr(tx_info, "model_dump") else str(tx_info))
        tx_hash = snapshot.get("tx_hash", "0x0") if isinstance(snapshot, dict) else "0x0"
        self.hub.publish_event(
            event_type="trade_telemetry",
            role=role,
            token=f"Trade executed: tx_hash={tx_hash}",
            snapshot=snapshot if isinstance(snapshot, dict) else {"tx": snapshot},
        )
