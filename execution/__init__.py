"""
Antigravity Execution & Pre-Broadcast Safety Subsystem (Milestone 2 - Features F08–F14).

Exports:
- Dual-Engine Wallet Integration: HotKeystoreSigner, EIP1193BridgeServer, DualEngineWalletRouter
- 5-Layer Pre-Broadcast Safety Pipeline: PreBroadcastGuardrailPipeline
- Multi-DEX Execution Router: MultiDEXRouter, DEXRouterConfig, KNOWN_DEX_CONFIGS
- Interface Contracts: GuardrailVerdict, ChainExecutionConfig, SwapTransactionRequest, SwapExecutionResult
"""
from execution.wallet.hot_signer import HotKeystoreSigner
from execution.wallet.eip1193_bridge import EIP1193BridgeServer, create_bridge_app
from execution.wallet.router import DualEngineWalletRouter
from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from execution.routers.dex_router import (
    KNOWN_DEX_CONFIGS,
    DEXRouterConfig,
    MultiDEXRouter,
)
from tests.e2e.contracts import (
    ChainExecutionConfig,
    GuardrailVerdict,
    SwapExecutionResult,
    SwapTransactionRequest,
)

__all__ = [
    # Wallet Integration
    "HotKeystoreSigner",
    "EIP1193BridgeServer",
    "create_bridge_app",
    "DualEngineWalletRouter",
    # Pre-Broadcast Safety Pipeline
    "PreBroadcastGuardrailPipeline",
    # Multi-DEX Routers
    "MultiDEXRouter",
    "DEXRouterConfig",
    "KNOWN_DEX_CONFIGS",
    # Shared Interface Contracts
    "ChainExecutionConfig",
    "GuardrailVerdict",
    "SwapExecutionResult",
    "SwapTransactionRequest",
]
