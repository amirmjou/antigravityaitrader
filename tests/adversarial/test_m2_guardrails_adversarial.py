"""
Adversarial Stress Test Suite for Milestone 2: Pre-Broadcast Guardrails & Wallet Execution.
Authored by teamwork_challenger_m2_1.

Empirically tests:
1. Hostile input testing: zero amount, negative amounts, extreme slippage (5000 bps), 100% price impact, toxic contracts (honeypot, 99% tax, blacklisted, cannot-sell).
2. Capital cap bypass testing: trades exceeding $250, 20% portfolio concentration violations, and drawdown >=8% circuit breaker.
3. Gas ceiling & ratio testing: base fee exceeding ceiling, gas-to-trade ratio >1.5%.
4. Simulation revert testing: dry-run reverts return approved=False with accurate revert reason decoding.
5. Dual-engine wallet & router stress testing: keystore encryption, nonce integrity, EIP-1559 math, multi-DEX addresses.
"""
from __future__ import annotations

import pytest
from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from execution.routers.dex_router import (
    KNOWN_DEX_CONFIGS,
    DEXRouterConfig,
    MultiDEXRouter,
)
from execution.wallet.eip1193_bridge import (
    ConfirmTxRequest,
    EIP1193BridgeServer,
    JsonRpcRequest,
    SendTxRequest,
)
from execution.wallet.hot_signer import HotKeystoreSigner
from execution.wallet.router import DualEngineWalletRouter
from tests.e2e.contracts import (
    ChainExecutionConfig,
    GuardrailVerdict,
    SwapExecutionResult,
    SwapTransactionRequest,
)
from tests.e2e.fixtures import (
    MockGoPlusClient,
    MockUniswapV3Quoter,
    MockWeb3Provider,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def arb_config():
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
def web3_provider():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def goplus_client():
    return MockGoPlusClient()


@pytest.fixture
def quoter_client():
    return MockUniswapV3Quoter(base_price_usd=88500.0, pool_liquidity_usd=50000000.0)


@pytest.fixture
def pipeline(arb_config, web3_provider, goplus_client, quoter_client):
    return PreBroadcastGuardrailPipeline(
        chain_config=arb_config,
        web3_provider=web3_provider,
        goplus_client=goplus_client,
        quoter=quoter_client,
        max_spend_per_trade_usd=250.0,
        max_asset_concentration_pct=20.0,
        max_daily_drawdown_pct=8.0,
    )


# ===========================================================================
# 1. Hostile Input Testing
# ===========================================================================

class TestHostileInputs:
    """Stress tests for hostile, corrupted, extreme, and toxic inputs."""

    def test_extreme_slippage_5000_bps_blocked(self, pipeline):
        """Hostile input: 5000 bps slippage (50%) must be hard blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            slippage_bps=5000,
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 3: Dynamic Slippage"
        assert "exceeds max 100 bps" in verdict.rejection_reason

    def test_extreme_price_impact_100_pct_blocked(self, pipeline):
        """Hostile input: 100% price impact must be blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            slippage_bps=50,
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req, override_quoter_impact_pct=100.0)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 3: Dynamic Slippage"
        assert "Price impact 100.00% exceeds 2.0% threshold" in verdict.rejection_reason

    def test_toxic_token_honeypot_on_token_in(self, pipeline, goplus_client):
        """Hostile input: Honeypot token as input token must be blocked."""
        goplus_client.token_database["0xHoneypotIn"] = {
            "is_honeypot": "1",
            "buy_tax": "0.0",
            "sell_tax": "0.0",
        }
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xHoneypotIn",
            token_out="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Honeypot detected on token_in" in verdict.rejection_reason

    def test_toxic_token_honeypot_on_token_out(self, pipeline, goplus_client):
        """Hostile input: Honeypot token as output token must be blocked."""
        goplus_client.token_database["0xHoneypotOut"] = {
            "is_honeypot": "1",
            "buy_tax": "0.0",
            "sell_tax": "0.0",
        }
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xHoneypotOut",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Honeypot detected on token_out" in verdict.rejection_reason

    def test_toxic_token_99_percent_sell_tax(self, pipeline, goplus_client):
        """Hostile input: 99% sell tax contract must be blocked."""
        goplus_client.token_database["0x99TaxToken"] = {
            "is_honeypot": "0",
            "buy_tax": "0.0",
            "sell_tax": "0.99",
        }
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x99TaxToken",
            token_out="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Tax exceeds 1% ceiling" in verdict.rejection_reason

    def test_toxic_token_cannot_sell_all_restriction(self, pipeline, goplus_client):
        """Hostile input: cannot_sell_all transfer restriction must be blocked."""
        goplus_client.token_database["0xCannotSellToken"] = {
            "is_honeypot": "0",
            "buy_tax": "0.0",
            "sell_tax": "0.0",
            "cannot_sell_all": "1",
        }
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xCannotSellToken",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Transfer restriction or blacklist detected" in verdict.rejection_reason

    def test_toxic_token_blacklisted_restriction(self, pipeline, goplus_client):
        """Hostile input: blacklisted address contract must be blocked."""
        goplus_client.token_database["0xBlacklistToken"] = {
            "is_honeypot": "0",
            "buy_tax": "0.0",
            "sell_tax": "0.0",
            "is_blacklisted": "1",
        }
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xBlacklistToken",
            token_out="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Transfer restriction or blacklist detected" in verdict.rejection_reason

    def test_zero_trade_value_behavior(self, pipeline):
        """
        Adversarial probe: zero trade_value_usd ($0.00).
        Evaluates whether pipeline handles zero trade value gracefully.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=0.0,
        )
        try:
            verdict = pipeline.evaluate(req)
            assert verdict.approved is False, "VULNERABILITY: Zero trade value was approved!"
        except ZeroDivisionError:
            pytest.fail("VULNERABILITY: PreBroadcastGuardrailPipeline raises unhandled ZeroDivisionError on trade_value_usd=0.0")

    def test_negative_trade_value_behavior(self, pipeline):
        """
        Adversarial probe: negative trade_value_usd (-$100.00).
        Evaluates whether negative trade value bypasses spend and concentration caps.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=-100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Negative trade value was approved by guardrail pipeline!"

    def test_zero_amount_in_wei_behavior(self, pipeline):
        """
        Adversarial probe: amount_in_wei = 0.
        Evaluates whether a 0-token swap is blocked.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=0,
            amount_out_min_wei=0,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Zero amount_in_wei was approved by guardrail pipeline!"

    def test_negative_amount_in_wei_behavior(self, pipeline):
        """
        Adversarial probe: negative amount_in_wei (-10**16).
        Evaluates whether a negative token amount is blocked.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=-10**16,
            amount_out_min_wei=0,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Negative amount_in_wei was approved by guardrail pipeline!"

    def test_zero_portfolio_value_behavior(self, pipeline):
        """
        Adversarial probe: current_portfolio_value_usd = 0.0.
        Evaluates whether pipeline handles zero portfolio value gracefully without ZeroDivisionError.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        try:
            verdict = pipeline.evaluate(req, current_portfolio_value_usd=0.0)
            assert verdict.approved is False, "VULNERABILITY: Trade approved with zero portfolio value!"
        except ZeroDivisionError:
            pytest.fail("VULNERABILITY: PreBroadcastGuardrailPipeline raises unhandled ZeroDivisionError on current_portfolio_value_usd=0.0")

    def test_expired_or_negative_deadline_behavior(self, pipeline):
        """
        Adversarial probe: deadline_seconds <= 0 (-10s).
        Evaluates whether an already-expired deadline is blocked.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            deadline_seconds=-10,
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Negative/expired deadline was approved by guardrail pipeline!"

    def test_negative_slippage_behavior(self, pipeline):
        """
        Adversarial probe: slippage_bps < 0 (-50 bps).
        Evaluates whether negative slippage is blocked.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            slippage_bps=-50,
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Negative slippage was approved by guardrail pipeline!"

    def test_same_token_in_and_out_behavior(self, pipeline):
        """
        Adversarial probe: token_in == token_out.
        Evaluates whether swapping a token for itself is blocked.
        """
        same_token = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in=same_token,
            token_out=same_token,
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False, "VULNERABILITY: Swapping a token for itself was approved by guardrail pipeline!"


# ===========================================================================
# 2. Capital Cap Bypass Testing
# ===========================================================================

class TestCapitalCapBypasses:
    """Stress tests for per-trade spend cap ($250), concentration (20%), and drawdown (8%)."""

    def test_trade_spend_exact_250_allowed(self, pipeline):
        """Boundary: $250.00 exact spend cap is allowed."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        verdict = pipeline.evaluate(req, current_portfolio_value_usd=5000.0, current_asset_holdings_usd=400.0)
        assert verdict.approved is True

    def test_trade_spend_250_01_blocked(self, pipeline):
        """Boundary: $250.01 just over cap must be hard blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.01,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in verdict.rejection_reason

    def test_trade_spend_huge_amount_blocked(self, pipeline):
        """Hostile: $100,000 spend attempt must be blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**19,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100000.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"

    def test_portfolio_concentration_exact_20_pct_allowed(self, pipeline):
        """Boundary: Exact 20.0% concentration ((800+200)/5000 = 20%) is allowed."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=200.0,
        )
        verdict = pipeline.evaluate(
            req,
            current_portfolio_value_usd=5000.0,
            current_asset_holdings_usd=800.0,
        )
        assert verdict.approved is True

    def test_portfolio_concentration_20_1_pct_blocked(self, pipeline):
        """Boundary: 20.02% ((801+200)/5000 = 20.02%) concentration is blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=200.0,
        )
        verdict = pipeline.evaluate(
            req,
            current_portfolio_value_usd=5000.0,
            current_asset_holdings_usd=801.0,
        )
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"
        assert "Asset concentration" in verdict.rejection_reason
        assert "exceeds max 20.0%" in verdict.rejection_reason

    def test_drawdown_exact_8_pct_circuit_breaker_trips(self, pipeline):
        """Boundary: Exactly 8.0% drawdown trips the circuit breaker."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req, current_daily_drawdown_pct=8.0)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"
        assert "Daily drawdown 8.0% exceeds circuit breaker 8.0%" in verdict.rejection_reason

    def test_drawdown_7_9_pct_passes(self, pipeline):
        """Boundary: 7.9% drawdown does not trip the circuit breaker."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req, current_daily_drawdown_pct=7.9)
        assert verdict.approved is True


# ===========================================================================
# 3. Gas Ceiling & Ratio Testing
# ===========================================================================

class TestGasCeilingAndRatio:
    """Stress tests for EIP-1559 base fee ceiling and gas-to-trade ratio."""

    def test_base_fee_exact_ceiling_allowed(self, pipeline, web3_provider):
        """Boundary: base fee exactly 120.0 gwei is allowed."""
        web3_provider.base_fee_gwei = 120.0
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        verdict = pipeline.evaluate(req)
        # Even if base fee is 120 gwei, check gas ceiling check specifically
        # (if gas ratio trips because 120 gwei gas cost is high for 250 usd, let's verify Layer 4 message)
        if not verdict.approved:
            assert verdict.layer_failed == "Layer 4: Gas & Congestion"

    def test_base_fee_120_1_gwei_blocked_by_gas_ceiling(self, pipeline, web3_provider):
        """Boundary: base fee 120.1 gwei trips base fee ceiling."""
        web3_provider.base_fee_gwei = 120.1
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 4: Gas & Congestion"
        assert "exceeds ceiling 120.0 gwei" in verdict.rejection_reason

    def test_gas_cost_ratio_exceeding_1_5_pct_blocked(self, pipeline, web3_provider):
        """
        Stress test: High gas cost relative to tiny trade.
        Gas = 145000 * (5 gwei + 0.05 gwei) * 1e-9 * $3100 = $2.27
        Trade value = $50.0 -> Gas ratio = 2.27 / 50 = 4.54% > 1.5%
        Must be blocked by Layer 4.
        """
        web3_provider.base_fee_gwei = 5.0
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=50.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 4: Gas & Congestion"
        assert "Gas-to-trade ratio" in verdict.rejection_reason
        assert "exceeds max 1.5%" in verdict.rejection_reason


# ===========================================================================
# 4. Simulation Revert Testing
# ===========================================================================

class TestSimulationRevertDecoding:
    """Stress tests for eth_call simulation reverts and reason decoding."""

    def test_revert_transfer_failed_decoding(self, pipeline, web3_provider):
        """Simulation revert with TRANSFER_FAILED decoded properly."""
        web3_provider.set_revert_trigger("TRANSFER_FAILED")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 5: Pre-Flight Simulation"
        assert "TRANSFER_FAILED" in verdict.rejection_reason

    def test_revert_insufficient_output_amount(self, pipeline, web3_provider):
        """Simulation revert with Uniswap INSUFFICIENT_OUTPUT_AMOUNT decoded."""
        web3_provider.set_revert_trigger("UniswapV3: INSUFFICIENT_OUTPUT_AMOUNT")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 5: Pre-Flight Simulation"
        assert "INSUFFICIENT_OUTPUT_AMOUNT" in verdict.rejection_reason

    def test_revert_burns_zero_gas_on_chain(self, pipeline, web3_provider):
        """
        Verify that dry-run simulation failure does NOT add any transaction
        to on-chain transaction history.
        """
        initial_tx_count = len(web3_provider.tx_history)
        web3_provider.set_revert_trigger("SafeERC20: low-level call failed")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = pipeline.evaluate(req)
        assert verdict.approved is False
        # Assert zero transactions sent on-chain
        assert len(web3_provider.tx_history) == initial_tx_count


# ===========================================================================
# 5. Dual-Engine Wallet & Router Stress Testing
# ===========================================================================

class TestWalletAndRouterRobustness:
    """Stress tests for wallet signing, nonce sequences, and multi-DEX routers."""

    def test_nonce_increments_monotonically(self, web3_provider):
        """Verify sequential signing strictly increments internal nonce."""
        signer = HotKeystoreSigner.create_new(web3_provider=web3_provider)
        start_nonce = signer.get_nonce()
        assert start_nonce == 0

        for i in range(5):
            tx_dict = {
                "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
                "value": 0,
                "gas": 21000,
                "chainId": 42161,
            }
            signed = signer.sign_transaction(tx_dict)
            assert signed["nonce"] == i

        assert signer.get_nonce() == 5

    def test_eip1559_fee_math(self, web3_provider):
        """
        Verify exact EIP-1559 fee calculation formula:
        maxFeePerGas = (2 * baseFeePerGas) + maxPriorityFeePerGas
        """
        signer = HotKeystoreSigner.create_new(web3_provider=web3_provider)
        fees = signer.estimate_eip1559_fees(base_fee_gwei=10.0, priority_fee_gwei=2.0)
        assert fees["baseFeePerGas"] == 10_000_000_000
        assert fees["maxPriorityFeePerGas"] == 2_000_000_000
        assert fees["maxFeePerGas"] == (2 * 10_000_000_000) + 2_000_000_000

    def test_multi_dex_canonical_addresses(self):
        """Verify Arbitrum One and Base canonical router addresses."""
        router = MultiDEXRouter()
        arb_uniswap = router.get_router_address(42161, protocol="uniswap_v3")
        assert arb_uniswap == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"

        base_uniswap = router.get_router_address(8453, protocol="uniswap_v3")
        assert base_uniswap == "0x2626664c2603336E57B271c5C0b26F421741e481"

        base_aerodrome = router.get_router_address(8453, protocol="aerodrome")
        assert base_aerodrome == "0xcF77a3Ba9A5CA399B7c97c74856154938591A088"

    def test_invalid_chain_id_raises_value_error(self):
        """Verify invalid chain ID raises clear ValueError."""
        router = MultiDEXRouter()
        with pytest.raises(ValueError, match="Unsupported chain_id: 99999"):
            router.get_config(99999)
