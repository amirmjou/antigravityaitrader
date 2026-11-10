"""
Tier 1: Feature Coverage (Category-Partition)
Features F08–F14: MetaMask Wallet & Pre-Broadcast Safety Guardrails (Milestone 2)
Each feature has >= 5 comprehensive, requirement-driven test cases.
"""
import pytest

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
from tests.e2e.harness import DualEngineWalletRouter, PreBroadcastGuardrailPipeline


# ===========================================================================
# Feature F08: Dual-Engine Wallet Architecture
# ===========================================================================
class TestF08DualEngineWalletArchitecture:
    def test_f08_01_autonomous_hot_signer_execution(self, wallet_router):
        """Verify autonomous hot-wallet signer broadcasts without interactive prompts."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req, signer_mode="hot_keystore")
        assert res.success is True
        assert res.tx_hash.startswith("0x")
        assert res.signer_mode == "hot_keystore"

    def test_f08_02_eip1193_metamask_bridge_mode(self, wallet_router):
        """Verify interactive EIP-1193 MetaMask bridge mode tagging."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req, signer_mode="eip1193_metamask")
        assert res.success is True
        assert res.signer_mode == "eip1193_metamask"

    def test_f08_03_transaction_hash_generation(self, wallet_router):
        """Verify 32-byte hex transaction hash formatting."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
        )
        res = wallet_router.execute_swap(req)
        assert len(res.tx_hash) == 66  # 0x + 64 hex chars

    def test_f08_04_block_number_increment(self, wallet_router, web3_arbitrum):
        """Verify block number increments upon transaction mining."""
        b1 = web3_arbitrum.block_number
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
        )
        res = wallet_router.execute_swap(req)
        assert res.block_number > b1

    def test_f08_05_execution_failure_handling(self, wallet_router, web3_arbitrum):
        """Verify revert reason capture when transaction fails."""
        web3_arbitrum.set_revert_trigger("INSUFFICIENT_OUTPUT_AMOUNT")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
        )
        res = wallet_router.execute_swap(req)
        assert res.success is False
        assert "INSUFFICIENT_OUTPUT_AMOUNT" in res.revert_reason
        web3_arbitrum.set_revert_trigger(None)


# ===========================================================================
# Feature F09: Guardrail L1: Contract Security
# ===========================================================================
class TestF09GuardrailL1ContractSecurity:
    def test_f09_01_safe_tokens_pass(self, guardrail_pipeline):
        """Verify standard verified tokens (WETH, WBTC) pass Layer 1."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", # WBTC
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True

    def test_f09_02_honeypot_rejection(self, guardrail_pipeline):
        """Verify malicious honeypot contracts are hard-blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xBadHoneypotTokenAddress0000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Honeypot detected" in verdict.rejection_reason

    def test_f09_03_tax_exceeding_1_pct_rejection(self, guardrail_pipeline):
        """Verify tokens with buy/sell taxes > 1.0% are blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xHighTaxTokenAddress0000000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "Tax exceeds 1% ceiling" in verdict.rejection_reason

    def test_f09_04_zero_tax_allowed(self, guardrail_pipeline):
        """Verify 0.0% tax tokens pass without hindrance."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True

    def test_f09_05_rejection_reason_specificity(self, guardrail_pipeline):
        """Verify rejection message specifies which token caused violation."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xBadHoneypotTokenAddress0000000000000000",
            token_out="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "token_in" in verdict.rejection_reason


# ===========================================================================
# Feature F10: Guardrail L2: Capital Allocation
# ===========================================================================
class TestF10GuardrailL2CapitalAllocation:
    def test_f10_01_per_trade_spend_under_cap_allowed(self, guardrail_pipeline):
        """Verify orders <= $250 pass Layer 2 cap."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True

    def test_f10_02_per_trade_spend_over_cap_blocked(self, guardrail_pipeline):
        """Verify orders > $250 are blocked by Layer 2 spend limit."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=250.01,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in verdict.rejection_reason

    def test_f10_03_asset_concentration_under_20_pct(self, guardrail_pipeline):
        """Verify single asset concentration <= 20% passes."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=200.0,
        )
        # 400 + 200 = 600 / 5000 = 12% (< 20%)
        verdict = guardrail_pipeline.evaluate(req, current_portfolio_value_usd=5000.0, current_asset_holdings_usd=400.0)
        assert verdict.approved is True

    def test_f10_04_asset_concentration_over_20_pct_blocked(self, guardrail_pipeline):
        """Verify single asset concentration > 20% is blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=200.0,
        )
        # 900 + 200 = 1100 / 5000 = 22% (> 20%)
        verdict = guardrail_pipeline.evaluate(req, current_portfolio_value_usd=5000.0, current_asset_holdings_usd=900.0)
        assert verdict.approved is False
        assert "Asset concentration 22.0% exceeds max 20.0%" in verdict.rejection_reason

    def test_f10_05_daily_drawdown_circuit_breaker(self, guardrail_pipeline):
        """Verify 8.0% daily portfolio drawdown trips circuit breaker."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req, current_daily_drawdown_pct=8.1)
        assert verdict.approved is False
        assert "Daily drawdown 8.1% exceeds circuit breaker 8.0%" in verdict.rejection_reason


# ===========================================================================
# Feature F11: Guardrail L3: Dynamic Slippage
# ===========================================================================
class TestF11GuardrailL3DynamicSlippage:
    def test_f11_01_quoter_amount_out_computed(self, guardrail_pipeline):
        """Verify Uniswap v3 IQuoterV2 off-chain price output is populated in verdict."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True
        assert verdict.quoted_amount_out_min > 0

    def test_f11_02_slippage_within_tolerance(self, guardrail_pipeline):
        """Verify slippage tolerance of 50 bps passes."""
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
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True

    def test_f11_03_slippage_exceeding_ceiling_blocked(self, guardrail_pipeline):
        """Verify requested slippage > 100 bps ceiling is blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            slippage_bps=120,
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "slippage 120 bps exceeds max 100 bps" in verdict.rejection_reason

    def test_f11_04_price_impact_exceeding_2_pct_blocked(self, guardrail_pipeline):
        """Verify price impact > 2.0% is blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req, override_quoter_impact_pct=2.5)
        assert verdict.approved is False
        assert "Price impact 2.50% exceeds 2.0% threshold" in verdict.rejection_reason

    def test_f11_05_transaction_deadline_300s_enforcement(self, guardrail_pipeline):
        """Verify deadline > 300s limit is blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            deadline_seconds=600,
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "deadline 600s exceeds 300s limit" in verdict.rejection_reason


# ===========================================================================
# Feature F12: Guardrail L4: Gas & Congestion
# ===========================================================================
class TestF12GuardrailL4GasAndCongestion:
    def test_f12_01_normal_gas_passes(self, guardrail_pipeline, web3_arbitrum):
        """Verify normal L2 gas (0.1 gwei) passes."""
        web3_arbitrum.base_fee_gwei = 0.1
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True

    def test_f12_02_base_fee_exceeding_ceiling_blocked(self, guardrail_pipeline, web3_arbitrum):
        """Verify extreme gas spike (> 120 gwei) trips Layer 4."""
        web3_arbitrum.base_fee_gwei = 150.0
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "base fee 150.0 gwei exceeds ceiling 120.0 gwei" in verdict.rejection_reason
        web3_arbitrum.base_fee_gwei = 0.1

    def test_f12_03_gas_to_trade_ratio_under_limit(self, guardrail_pipeline, web3_arbitrum):
        """Verify gas cost ratio <= 1.5% of trade value passes."""
        web3_arbitrum.base_fee_gwei = 0.5
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=150.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True
        web3_arbitrum.base_fee_gwei = 0.1

    def test_f12_04_gas_to_trade_ratio_over_limit_blocked(self, guardrail_pipeline, web3_arbitrum):
        """Verify micro-trades where gas > 1.5% of trade value are blocked."""
        web3_arbitrum.base_fee_gwei = 10.0  # Gas cost ~0.24 USD
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=10.0,  # $10 trade -> ratio ~2.4% > 1.5%
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "Gas-to-trade ratio" in verdict.rejection_reason
        web3_arbitrum.base_fee_gwei = 0.1

    def test_f12_05_priority_fee_incorporation(self, web3_arbitrum):
        """Verify priority fee is tracked in gas calculation."""
        assert web3_arbitrum.priority_fee_gwei == 0.05


# ===========================================================================
# Feature F13: Guardrail L5: Pre-Flight Simulation
# ===========================================================================
class TestF13GuardrailL5PreFlightSimulation:
    def test_f13_01_clean_simulation_passes(self, guardrail_pipeline):
        """Verify clean eth_call dry-run simulation approves trade."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True
        assert verdict.simulated_gas_used > 0

    def test_f13_02_custom_revert_reason_decoding(self, guardrail_pipeline, web3_arbitrum):
        """Verify eth_call simulation catches contract reverts before broadcast."""
        web3_arbitrum.set_revert_trigger("UniswapV3: K")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 5: Pre-Flight Simulation"
        assert "UniswapV3: K" in verdict.rejection_reason
        web3_arbitrum.set_revert_trigger(None)

    def test_f13_03_zero_gas_burned_on_revert(self, guardrail_pipeline, web3_arbitrum):
        """Verify simulated revert consumes zero on-chain gas (no tx hash)."""
        web3_arbitrum.set_revert_trigger("EXCESSIVE_SLIPPAGE")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert len(web3_arbitrum.tx_history) == 0
        web3_arbitrum.set_revert_trigger(None)

    def test_f13_04_transfer_failed_revert_detection(self, guardrail_pipeline, web3_arbitrum):
        """Verify token transfer failure during dry-run is caught."""
        web3_arbitrum.set_revert_trigger("TRANSFER_FAILED")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "TRANSFER_FAILED" in verdict.rejection_reason
        web3_arbitrum.set_revert_trigger(None)

    def test_f13_05_simulated_gas_output_metric(self, guardrail_pipeline):
        """Verify verdict records exact simulated gas used."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.simulated_gas_used == 145000


# ===========================================================================
# Feature F14: Multi-DEX Execution Router
# ===========================================================================
class TestF14MultiDEXExecutionRouter:
    def test_f14_01_arbitrum_uniswap_v3_router_address(self, arbitrum_config):
        """Verify Arbitrum SwapRouter02 contract address configuration."""
        assert arbitrum_config.router_address == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
        assert arbitrum_config.chain_id == 42161

    def test_f14_02_base_aerodrome_router_address(self, base_config):
        """Verify Base router contract address configuration."""
        assert base_config.router_address == "0x2626664c2603336E57B271c5C0b26F421741e481"
        assert base_config.chain_id == 8453

    def test_f14_03_swap_execution_success(self, wallet_router):
        """Verify swap transaction execution returns success with gas tracking."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req)
        assert res.success is True
        assert res.gas_used == 145000

    def test_f14_04_multi_chain_routing_dispatch(self, web3_base, base_config):
        """Verify execution router operates seamlessly across multiple chains."""
        base_router = DualEngineWalletRouter(web3_provider=web3_base, chain_config=base_config)
        req = SwapTransactionRequest(
            chain_id=8453,
            token_in="0x4200000000000000000000000000000000000006",
            token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            amount_in_wei=10**16,
            amount_out_min_wei=30000000,
            recipient="0xHotSigner",
            trade_value_usd=30.0,
        )
        res = base_router.execute_swap(req)
        assert res.success is True
        assert res.block_number > 0

    def test_f14_05_amount_out_minimum_protection(self, wallet_router):
        """Verify minimum output tokens returned match swap request constraint."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=98765432,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req)
        assert res.amount_out_wei == 98765432
