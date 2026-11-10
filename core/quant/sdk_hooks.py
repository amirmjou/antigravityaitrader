"""Antigravity Core SDK Hook Protocol Inspector & Execution Trigger Registry.

Integrates lifecycle hook protocols inspected from `google-antigravity/antigravity-sdk-python`
(`google.antigravity.hooks.hooks` and `google.antigravity.types`):
- `on_session_start`
- `on_session_end`
- `pre_turn`
- `post_turn`
- `pre_tool_call_decide`
- `post_tool_call`
- `on_tool_error`
- `on_compaction`
- `on_interaction`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    from google.antigravity import LocalAgentConfig, types
    from google.antigravity.hooks import hooks as agy_hooks

    HAS_AGY_SDK = True
except ImportError:  # pragma: no cover
    LocalAgentConfig = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    agy_hooks = None  # type: ignore[assignment]
    HAS_AGY_SDK = False


@dataclass(frozen=True)
class HookEventRecord:
    """Telemetry record captured by an Antigravity SDK lifecycle hook."""

    hook_type: str
    timestamp: str
    payload_summary: str
    allowed: bool = True


class AntigravityHookProtocolManager:
    """Manages Antigravity SDK lifecycle hooks and pre-turn slash-command triggers."""

    SUPPORTED_HOOK_PROTOCOLS: tuple[str, ...] = (
        "on_session_start",
        "on_session_end",
        "pre_turn",
        "post_turn",
        "pre_tool_call_decide",
        "post_tool_call",
        "on_tool_error",
        "on_compaction",
        "on_interaction",
    )

    def __init__(self) -> None:
        self._event_log: List[HookEventRecord] = []
        self._slash_triggers: Dict[str, Callable[[str], Any]] = {}
        self._sdk_hooks: List[Any] = []
        if HAS_AGY_SDK:
            self._wire_sdk_hooks()

    @property
    def event_log(self) -> List[HookEventRecord]:
        return list(self._event_log)

    @property
    def registered_triggers(self) -> List[str]:
        return sorted(self._slash_triggers.keys())

    def register_slash_trigger(self, command: str, handler: Callable[[str], Any]) -> None:
        """Bind a slash command (e.g. '/full-analysis') to a local trigger callback."""
        norm = command.strip().lower()
        if not norm.startswith("/"):
            norm = f"/{norm}"
        self._slash_triggers[norm] = handler

    def _record(self, hook_type: str, summary: str, allowed: bool = True) -> None:
        self._event_log.append(
            HookEventRecord(
                hook_type=hook_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload_summary=summary,
                allowed=allowed,
            )
        )

    def _wire_sdk_hooks(self) -> None:
        """Decorate lifecycle callbacks using `google.antigravity.hooks.hooks`."""

        @agy_hooks.on_session_start
        async def on_trading_session_start() -> None:
            self._record("on_session_start", "Quantitative trading session initialized.")

        @agy_hooks.on_session_end
        async def on_trading_session_end() -> None:
            self._record("on_session_end", "Quantitative trading session closed.")

        @agy_hooks.pre_turn
        async def on_trading_pre_turn(prompt: str) -> Any:
            self._record("pre_turn", f"User prompt inspected ({len(prompt)} chars).")
            return types.HookResult(allow=True)

        @agy_hooks.post_turn
        async def on_trading_post_turn(response: str) -> None:
            self._record("post_turn", f"Model response observed ({len(response)} chars).")

        @agy_hooks.pre_tool_call_decide
        async def on_trading_pre_tool_call(data: Any) -> Any:
            tool_name = getattr(data, "name", str(data))
            self._record("pre_tool_call_decide", f"Tool call approved: {tool_name}")
            return types.HookResult(allow=True)

        @agy_hooks.post_tool_call
        async def on_trading_post_tool_call(data: Any) -> None:
            tool_name = getattr(data, "name", str(data))
            self._record("post_tool_call", f"Tool call completed: {tool_name}")

        @agy_hooks.on_tool_error
        async def on_trading_tool_error(data: Any) -> None:
            self._record("on_tool_error", f"Tool error observed: {data}", allowed=False)
            return None

        self._sdk_hooks = [
            on_trading_session_start,
            on_trading_session_end,
            on_trading_pre_turn,
            on_trading_post_turn,
            on_trading_pre_tool_call,
            on_trading_post_tool_call,
            on_trading_tool_error,
        ]

    def build_local_agent_config(self, extra_tools: Optional[List[Callable[..., Any]]] = None) -> Any:
        """Construct a `google.antigravity.LocalAgentConfig` pre-wired with trading hooks."""
        if not HAS_AGY_SDK:
            return {"hooks": len(self._sdk_hooks), "tools": len(extra_tools or [])}
        return LocalAgentConfig(
            hooks=list(self._sdk_hooks),
            tools=list(extra_tools or []),
            capabilities=types.CapabilitiesConfig(
                agent_behavior=types.AgentBehavior.INTERACTIVE,
                enable_subagents=True,
            ),
        )

    def inspect_protocol_status(self) -> Dict[str, Any]:
        """Return verification status of the Antigravity Python SDK hook protocols."""
        return {
            "sdk_installed": HAS_AGY_SDK,
            "supported_hooks": list(self.SUPPORTED_HOOK_PROTOCOLS),
            "wired_hook_count": len(self._sdk_hooks),
            "registered_slash_triggers": self.registered_triggers,
            "recorded_events": len(self._event_log),
        }
