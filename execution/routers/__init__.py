"""
DEX Routers Module.
Provides MultiDEXRouter and canonical network DEX configurations.
"""
from execution.routers.dex_router import (
    KNOWN_DEX_CONFIGS,
    DEXRouterConfig,
    MultiDEXRouter,
)

__all__ = [
    "DEXRouterConfig",
    "KNOWN_DEX_CONFIGS",
    "MultiDEXRouter",
]
