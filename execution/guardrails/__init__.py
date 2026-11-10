"""
Guardrails module.
Provides PreBroadcastGuardrailPipeline coordinating 5-layer safety checks:
Contract Security, Capital Allocation, Dynamic Slippage, Gas & Congestion, Pre-Flight Simulation.
"""
from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline

__all__ = [
    "PreBroadcastGuardrailPipeline",
]
