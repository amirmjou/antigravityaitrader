"""
Wallet Integration Module.
Provides autonomous hot keystore signing, interactive EIP-1193 MetaMask bridge,
and dual-engine execution routing.
"""
from execution.wallet.hot_signer import HotKeystoreSigner
from execution.wallet.eip1193_bridge import EIP1193BridgeServer, create_bridge_app
from execution.wallet.router import DualEngineWalletRouter

__all__ = [
    "HotKeystoreSigner",
    "EIP1193BridgeServer",
    "create_bridge_app",
    "DualEngineWalletRouter",
]
