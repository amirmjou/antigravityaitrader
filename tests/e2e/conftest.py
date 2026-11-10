"""
Pytest configuration and shared fixtures for the E2E test suite.
"""
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import pytest

from tests.e2e.contracts import ChainExecutionConfig, ThinkingLevel
from tests.e2e.fixtures import (
    LocalJevMCPClient,
    MockCCXTExchange,
    MockGeminiAntigravityClient,
    MockGoPlusClient,
    MockPublicAPIs,
    MockRemoteAgentBridge,
    MockUniswapV3Quoter,
    MockWeb3Provider,
)
from tests.e2e.harness import (
    CryptoIngestionSizingEngine,
    DualEngineWalletRouter,
    MultiAgentDeliberationEngine,
    PaperTradingEngine,
    PreBroadcastGuardrailPipeline,
    VisualizationStreamHub,
)


@pytest.fixture
def web3_arbitrum():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def web3_base():
    return MockWeb3Provider(chain_id=8453, base_fee_gwei=0.005)


@pytest.fixture
def goplus_client():
    return MockGoPlusClient()


@pytest.fixture
def uniswap_quoter():
    return MockUniswapV3Quoter(base_price_usd=88500.0, pool_liquidity_usd=50000000.0)


@pytest.fixture
def arbitrum_config():
    return ChainExecutionConfig(
        chain_id=42161,
        chain_name="Arbitrum One",
        rpc_url="https://arb1.arbitrum.io/rpc",
        router_address="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        quoter_address="0x61fFE014bA136170505655d03170F09287640F16",
        default_slippage_bps=50,
        max_slippage_bps=100,
        gas_ceiling_gwei=120.0,
        gas_cost_ratio_max_pct=1.5,
    )


@pytest.fixture
def base_config():
    return ChainExecutionConfig(
        chain_id=8453,
        chain_name="Base",
        rpc_url="https://mainnet.base.org",
        router_address="0x2626664c2603336E57B271c5C0b26F421741e481",
        default_slippage_bps=50,
        max_slippage_bps=100,
        gas_ceiling_gwei=120.0,
        gas_cost_ratio_max_pct=1.5,
    )


@pytest.fixture
def guardrail_pipeline(arbitrum_config, web3_arbitrum, goplus_client, uniswap_quoter):
    return PreBroadcastGuardrailPipeline(
        chain_config=arbitrum_config,
        web3_provider=web3_arbitrum,
        goplus_client=goplus_client,
        quoter=uniswap_quoter,
        max_spend_per_trade_usd=250.0,
        max_asset_concentration_pct=20.0,
        max_daily_drawdown_pct=8.0,
    )


@pytest.fixture
def multi_agent_engine():
    return MultiAgentDeliberationEngine(thinking_level=ThinkingLevel.HIGH)


@pytest.fixture
def wallet_router(web3_arbitrum, arbitrum_config):
    return DualEngineWalletRouter(web3_provider=web3_arbitrum, chain_config=arbitrum_config)


@pytest.fixture
def stream_hub():
    return VisualizationStreamHub()


@pytest.fixture
def crypto_sizing_engine():
    return CryptoIngestionSizingEngine()


@pytest.fixture
def paper_trader():
    return PaperTradingEngine(initial_cash_usd=10000.0)


@pytest.fixture
def jev_client():
    return LocalJevMCPClient()
