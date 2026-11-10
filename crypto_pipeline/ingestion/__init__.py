"""Market data ingestion feeds for CCXT, Alternative.me, and DeFiLlama (Feature F19)."""
from crypto_pipeline.ingestion.feeds import (
    AlternativeMeFearGreedFeed,
    CCXTMarketFeed,
    DeFiLlamaTVLFeed,
)

__all__ = ["AlternativeMeFearGreedFeed", "CCXTMarketFeed", "DeFiLlamaTVLFeed"]
