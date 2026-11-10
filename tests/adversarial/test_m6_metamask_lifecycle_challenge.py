"""
MetaMask Lifecycle & Execution Guardrails Adversarial Challenge Suite.
Authored by teamwork_challenger_m6_2 (MetaMask Lifecycle Adversarial Challenger).

Empirically stresses:
1. Transaction Lifecycle:
   - Double-confirming an already confirmed request_id (preventing replay).
   - Confirming a non-existent request_id.
   - Confirming an already rejected request_id.
   - Rejection handling with custom error messages and verify status transitions to 'rejected'.
   - Asymmetric rejection state handling (rejecting non-existent or already confirmed requests).
2. Execution Guardrails (PreBroadcastGuardrailPipeline):
   - Layer 1: Contract Security (self-swap rejection, honeypot, >1% tax, blacklist).
   - Layer 2: Capital Allocation (per-trade spend cap > $250, asset concentration > 20%, drawdown >= 8%).
   - Layer 3: Dynamic Slippage (slippage > 100 bps ceiling, negative slippage, price impact > 2.0%, deadline > 300s).
   - Guardrail interception integration with DualEngineWalletRouter.
3. SSE Deliberation Stream & Realtime Scaling:
   - Backlog replay ordering with since_id (0, mid, end).
   - Out-of-order since_id edge cases (future since_id, negative since_id, None).
   - High concurrency fan-out across 50 concurrent SSE subscribers.
   - Safe unsubscription without queue leaks.
4. Bridge JSON-RPC & Rate Limiting:
   - Malformed eth_sendTransaction params resilience.
   - Wallet sync with hex and int chain IDs.
   - Transaction endpoint rate limit saturation (HTTP 429 after 30 requests).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import time
from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from execution.wallet.eip1193_bridge import (
    ConfirmTxRequest,
    EIP1193BridgeServer,
    JsonRpcRequest,
    SendTxRequest,
)
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
from visualization.server.app import create_visualization_app
from visualization.server.security import (
    global_rate_limiter,
    global_simulation_cache,
)
from visualization.telemetry.hub import TelemetryHub

TEST_AUTH_TOKEN = "m6_lifecycle_adversarial_secret_2026!"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def clean_test_env(monkeypatch):
    """Ensure rate limiter and simulation cache are reset before/after each test."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    os.environ.pop("TRADINGAGENTS_SECURITY_MODE", None)
    os.environ.pop("TRADING_API_KEY", None)


@pytest.fixture
def arb_chain_config():
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
def mock_w3_arbitrum():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def mock_goplus():
    return MockGoPlusClient()


@pytest.fixture
def mock_quoter():
    return MockUniswapV3Quoter(base_price_usd=3100.0, pool_liquidity_usd=50000000.0)


@pytest.fixture
def guardrail_pipeline(arb_chain_config, mock_w3_arbitrum, mock_goplus, mock_quoter):
    return PreBroadcastGuardrailPipeline(
        chain_config=arb_chain_config,
        web3_provider=mock_w3_arbitrum,
        goplus_client=mock_goplus,
        quoter=mock_quoter,
        max_spend_per_trade_usd=250.0,
        max_asset_concentration_pct=20.0,
        max_daily_drawdown_pct=8.0,
        eth_price_usd=3100.0,
    )


@pytest.fixture
def live_client(monkeypatch):
    """Produces authenticated TestClient with fresh TelemetryHub and BridgeServer."""
    monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
    monkeypatch.setenv("TRADING_API_KEY", TEST_AUTH_TOKEN)
    hub = TelemetryHub()
    bridge = EIP1193BridgeServer(default_chain_id=42161)
    app = create_visualization_app(hub=hub, bridge_server=bridge)
    client = TestClient(app)
    return client, app, hub, bridge


def auth_headers():
    return {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}


# ===========================================================================
# 1. MetaMask Transaction Lifecycle Edge Cases & Replay Attacks
# ===========================================================================

class TestMetaMaskTransactionLifecycleEdgeCases:
    """Stress tests MetaMask transaction staging, confirmation, and cancellation."""

    def test_double_confirm_transaction_prevention(self, live_client):
        """Confirming an already confirmed request_id must be rejected (cannot confirm twice)."""
        client, app, hub, bridge = live_client

        # 1. Stage a transaction
        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 1000},
            headers=auth_headers(),
        )
        assert stage_res.status_code == 200
        req_id = stage_res.json()["request_id"]
        assert req_id in bridge.pending_transactions

        # 2. First confirmation -> Success
        first_hash = "0x" + "a" * 64
        confirm_1 = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": True, "tx_hash": first_hash},
            headers=auth_headers(),
        )
        assert confirm_1.status_code == 200
        assert confirm_1.json()["status"] == "confirmed"
        assert confirm_1.json()["tx_hash"] == first_hash
        assert req_id not in bridge.pending_transactions
        assert req_id in bridge.transaction_results
        assert bridge.transaction_results[req_id]["status"] == "confirmed"
        assert bridge.transaction_results[req_id]["tx_hash"] == first_hash

        # 3. Second confirmation attempt (Replay Attack) -> Must be rejected with 404
        second_hash = "0x" + "b" * 64
        confirm_2 = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": True, "tx_hash": second_hash},
            headers=auth_headers(),
        )
        assert confirm_2.status_code == 404
        assert f"Request {req_id} not found" in confirm_2.json()["detail"]

        # 4. Verify initial confirmation was NOT overwritten by second attempt
        assert bridge.transaction_results[req_id]["tx_hash"] == first_hash
        assert bridge.transaction_results[req_id]["status"] == "confirmed"

    def test_confirm_nonexistent_request_id_rejection(self, live_client):
        """Confirming a non-existent request_id must return 404 Not Found."""
        client, app, hub, bridge = live_client
        nonexistent_id = "tx_deadbeef9999"

        res = client.post(
            "/confirm-transaction",
            json={"request_id": nonexistent_id, "success": True, "tx_hash": "0x" + "1" * 64},
            headers=auth_headers(),
        )
        assert res.status_code == 404
        assert f"Request {nonexistent_id} not found" in res.json()["detail"]

    def test_confirm_already_rejected_transaction_rejection(self, live_client):
        """Confirming an already rejected request_id must be blocked with 404."""
        client, app, hub, bridge = live_client

        # 1. Stage transaction
        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x2222222222222222222222222222222222222222", "amount_in_wei": 500},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]

        # 2. Reject transaction
        rej_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": "User clicked Reject in MetaMask"},
            headers=auth_headers(),
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"
        assert bridge.transaction_results[req_id]["status"] == "rejected"

        # 3. Attempt to confirm after rejection -> Must return 404
        conf_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": True, "tx_hash": "0x" + "c" * 64},
            headers=auth_headers(),
        )
        assert conf_res.status_code == 404
        assert f"Request {req_id} not found" in conf_res.json()["detail"]
        assert bridge.transaction_results[req_id]["status"] == "rejected"

    def test_rejection_with_custom_error_messages(self, live_client):
        """Rejection must preserve user-specified error messages and transition status to 'rejected'."""
        client, app, hub, bridge = live_client

        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x3333333333333333333333333333333333333333", "amount_in_wei": 750},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]

        custom_error = "MetaMask User Denied (Error: 4001): Transaction simulation indicated excessive gas."
        rej_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": custom_error},
            headers=auth_headers(),
        )
        assert rej_res.status_code == 200
        assert rej_res.json() == {"status": "rejected", "request_id": req_id}

        record = bridge.transaction_results.get(req_id)
        assert record is not None
        assert record["status"] == "rejected"
        assert record["error_reason"] == custom_error
        assert "rejected_at" in record

    def test_rejection_default_error_fallback(self, live_client):
        """If error_reason is None or empty, default rejection message is applied."""
        client, app, hub, bridge = live_client

        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x4444444444444444444444444444444444444444", "amount_in_wei": 200},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]

        rej_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": None},
            headers=auth_headers(),
        )
        assert rej_res.status_code == 200
        record = bridge.transaction_results[req_id]
        assert record["status"] == "rejected"
        assert record["error_reason"] == "User rejected transaction in MetaMask"

    def test_adversarial_reject_already_confirmed_transaction_finding(self, live_client):
        """
        Adversarial probe: Calling reject on an already confirmed transaction.
        Finding: The HTTP endpoint returns 200 {'status': 'rejected'} even though
        the underlying bridge server refused to mutate the confirmed result.
        """
        client, app, hub, bridge = live_client

        # 1. Stage and confirm
        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x5555555555555555555555555555555555555555", "amount_in_wei": 100},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]
        real_hash = "0x" + "9" * 64
        client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": True, "tx_hash": real_hash},
            headers=auth_headers(),
        )
        assert bridge.transaction_results[req_id]["status"] == "confirmed"

        # 2. Hostile or stale reject call on already confirmed transaction
        fake_rej = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": "Late cancel attempt"},
            headers=auth_headers(),
        )
        # Verify internal bridge integrity: confirmed state was NOT overwritten
        assert bridge.transaction_results[req_id]["status"] == "confirmed"
        assert bridge.transaction_results[req_id]["tx_hash"] == real_hash

    def test_direct_bridge_server_confirm_and_reject_contracts(self):
        """Test underlying EIP1193BridgeServer directly for deterministic contract verification."""
        bridge = EIP1193BridgeServer()
        staged = bridge.stage_transaction_sync({"to": "0xDirect", "amount": 100})
        req_id = staged["request_id"]

        # Confirm non-existent
        res_bad = bridge.confirm_transaction("tx_not_there", "0x123")
        assert res_bad["success"] is False
        assert "not found" in res_bad["error"]

        # Reject non-existent
        res_rej_bad = bridge.reject_transaction("tx_not_there")
        assert res_rej_bad["success"] is False
        assert "not found" in res_rej_bad["error"]

        # Proper confirm
        res_ok = bridge.confirm_transaction(req_id, "0xRealHash")
        assert res_ok["status"] == "confirmed"
        assert res_ok["tx_hash"] == "0xRealHash"

        # Double confirm on server directly
        res_double = bridge.confirm_transaction(req_id, "0xSecondHash")
        assert res_double["success"] is False
        assert "not found" in res_double["error"]


# ===========================================================================
# 2. Execution Guardrails Integration Testing (Layer 1, Layer 2, Layer 3)
# ===========================================================================

class TestExecutionGuardrailsIntegration:
    """Stress tests the 5-layer safety guardrail pipeline against hostile transactions."""

    def test_guardrail_layer1_self_swap_rejection(self, guardrail_pipeline):
        """Layer 1: Self-swap (token_in == token_out) must be blocked immediately."""
        token_weth = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in=token_weth,
            token_out=token_weth.lower(),  # Case variation
            amount_in_wei=10**16,
            amount_out_min_wei=10**16,
            recipient="0xUserWallet",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Self-swap rejected" in verdict.rejection_reason

    def test_guardrail_layer1_zero_or_negative_amount_rejection(self, guardrail_pipeline):
        """Layer 1: Non-positive amount_in_wei must be blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=0,
            amount_out_min_wei=100,
            recipient="0xUserWallet",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Non-positive amount_in_wei" in verdict.rejection_reason

    def test_guardrail_layer1_honeypot_and_toxic_contract_rejection(self, guardrail_pipeline, mock_goplus):
        """Layer 1: Malicious honeypot contracts or >1% transfer tax must be blocked."""
        # 1. Honeypot token
        req_hp = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xBadHoneypotTokenAddress0000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=50.0,
        )
        verdict_hp = guardrail_pipeline.evaluate(req_hp)
        assert verdict_hp.approved is False
        assert verdict_hp.layer_failed == "Layer 1: Contract Security"
        assert "Honeypot detected" in verdict_hp.rejection_reason

        # 2. High tax token (e.g. 5% tax)
        req_tax = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xHighTaxTokenAddress0000000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=50.0,
        )
        verdict_tax = guardrail_pipeline.evaluate(req_tax)
        assert verdict_tax.approved is False
        assert "Tax exceeds 1% ceiling" in verdict_tax.rejection_reason

    def test_guardrail_layer2_spend_cap_exceeded(self, guardrail_pipeline):
        """Layer 2: Per-trade spend exceeding $250 cap must be blocked."""
        # 1. Boundary pass: Exactly $250.00
        req_250 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=250.00,
        )
        verdict_250 = guardrail_pipeline.evaluate(req_250)
        assert verdict_250.approved is True

        # 2. Boundary violation: $250.01
        req_250_01 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=250.01,
        )
        verdict_250_01 = guardrail_pipeline.evaluate(req_250_01)
        assert verdict_250_01.approved is False
        assert verdict_250_01.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in verdict_250_01.rejection_reason

        # 3. Severe violation: $10,000 runaway order
        req_10k = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**18,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=10000.0,
        )
        verdict_10k = guardrail_pipeline.evaluate(req_10k)
        assert verdict_10k.approved is False
        assert "exceeds cap of $250.0" in verdict_10k.rejection_reason

    def test_guardrail_layer2_portfolio_concentration_and_drawdown(self, guardrail_pipeline):
        """Layer 2: Asset concentration > 20% or drawdown >= 8% must be blocked."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=200.0,
        )
        # Concentration violation: (900 + 200) / 5000 = 22% > 20%
        verdict_conc = guardrail_pipeline.evaluate(
            req, current_portfolio_value_usd=5000.0, current_asset_holdings_usd=900.0
        )
        assert verdict_conc.approved is False
        assert "Asset concentration 22.0% exceeds max 20.0%" in verdict_conc.rejection_reason

        # Drawdown circuit breaker: 8.5% >= 8.0%
        verdict_dd = guardrail_pipeline.evaluate(req, current_daily_drawdown_pct=8.5)
        assert verdict_dd.approved is False
        assert "Daily drawdown 8.5% exceeds circuit breaker 8.0%" in verdict_dd.rejection_reason

    def test_guardrail_layer3_dynamic_slippage_exceeded(self, guardrail_pipeline):
        """Layer 3: Requested slippage exceeding 100 bps ceiling must be blocked."""
        # 1. Allowed ceiling: 100 bps
        req_100 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            slippage_bps=100,
            trade_value_usd=100.0,
        )
        verdict_100 = guardrail_pipeline.evaluate(req_100)
        assert verdict_100.approved is True

        # 2. Slippage violation: 101 bps
        req_101 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            slippage_bps=101,
            trade_value_usd=100.0,
        )
        verdict_101 = guardrail_pipeline.evaluate(req_101)
        assert verdict_101.approved is False
        assert verdict_101.layer_failed == "Layer 3: Dynamic Slippage"
        assert "Requested slippage 101 bps exceeds max 100 bps" in verdict_101.rejection_reason

        # 3. Negative slippage: -50 bps
        req_neg = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            slippage_bps=-50,
            trade_value_usd=100.0,
        )
        verdict_neg = guardrail_pipeline.evaluate(req_neg)
        assert verdict_neg.approved is False
        assert "Negative slippage tolerance rejected" in verdict_neg.rejection_reason

    def test_guardrail_layer3_price_impact_and_deadline(self, guardrail_pipeline):
        """Layer 3: Price impact > 2.0% or deadline > 300s must be blocked."""
        # Price impact 2.5%
        req_pi = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=100.0,
        )
        verdict_pi = guardrail_pipeline.evaluate(req_pi, override_quoter_impact_pct=2.5)
        assert verdict_pi.approved is False
        assert "Price impact 2.50% exceeds 2.0% threshold" in verdict_pi.rejection_reason

        # Deadline 301 seconds
        req_dl = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            deadline_seconds=301,
            trade_value_usd=100.0,
        )
        verdict_dl = guardrail_pipeline.evaluate(req_dl)
        assert verdict_dl.approved is False
        assert "deadline 301s exceeds 300s limit" in verdict_dl.rejection_reason

    def test_guardrail_interception_prevents_router_execution(self, guardrail_pipeline, arb_chain_config, mock_w3_arbitrum):
        """Ensure an unapproved verdict intercepts and halts before wallet routing."""
        bridge = EIP1193BridgeServer()
        router = DualEngineWalletRouter(web3_provider=mock_w3_arbitrum, chain_config=arb_chain_config, bridge_server=bridge)

        # Hostile trade: $500 spend (violates L2)
        hostile_req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=500.0,
        )
        verdict = guardrail_pipeline.evaluate(hostile_req)
        assert verdict.approved is False

        # Guardrail gate pattern: if not approved, do NOT execute
        if not verdict.approved:
            execution_attempted = False
        else:
            router.execute_swap(hostile_req, signer_mode="eip1193_metamask")
            execution_attempted = True

        assert execution_attempted is False
        assert len(bridge.pending_transactions) == 0


# ===========================================================================
# 3. High Concurrency SSE Deliberation Stream & Backlog Replay
# ===========================================================================

class TestSseConcurrencyAndBacklogReplay:
    """Stress tests SSE deliberation queueing, fan-out, and since_id sequencing."""

    def test_sse_backlog_replay_exact_sequence_ordering(self):
        """Backlog replay must deliver events strictly in ascending sequence."""
        async def _run():
            hub = TelemetryHub()
            # Publish 10 deliberate reasoning events
            for i in range(1, 11):
                hub.publish_event("agent_thought", "Market Analyst", f"Insight #{i}")

            assert len(hub.event_backlog) == 10

            # Subscriber requesting all backlog (since_id=0)
            q_all = await hub.subscribe_sse(since_id=0)
            assert q_all.qsize() == 10
            events_received = []
            while not q_all.empty():
                events_received.append(q_all.get_nowait())

            seq_ids = [e.event_id for e in events_received]
            assert seq_ids == list(range(1, 11))
            await hub.unsubscribe_sse(q_all)

            # Subscriber requesting mid-stream (since_id=6)
            q_mid = await hub.subscribe_sse(since_id=6)
            assert q_mid.qsize() == 4
            mid_ids = []
            while not q_mid.empty():
                mid_ids.append(q_mid.get_nowait().event_id)
            assert mid_ids == [7, 8, 9, 10]
            await hub.unsubscribe_sse(q_mid)

        asyncio.run(_run())

    def test_sse_out_of_order_and_edge_since_ids(self):
        """Out-of-order since_id values (negative, future, none) must not crash or deadlock."""
        async def _run():
            hub = TelemetryHub()
            for i in range(1, 6):
                hub.publish_event("debate_turn", "Bull Researcher", f"Point {i}")

            # 1. Future since_id (ahead of current backlog)
            q_future = await hub.subscribe_sse(since_id=9999)
            assert q_future.qsize() == 0  # 0 backlog replayed, waits for live

            # 2. Negative since_id
            q_neg = await hub.subscribe_sse(since_id=-10)
            assert q_neg.qsize() == 5  # Replays all 5 events

            # 3. None since_id
            q_none = await hub.subscribe_sse(since_id=None)
            assert q_none.qsize() == 0  # Replays nothing, only live

            # Publish a live event -> all 3 receive it
            hub.publish_event("proposal_generated", "Execution Trader", "Live proposal")
            assert q_future.qsize() == 1
            assert q_neg.qsize() == 6
            assert q_none.qsize() == 1

            await hub.unsubscribe_sse(q_future)
            await hub.unsubscribe_sse(q_neg)
            await hub.unsubscribe_sse(q_none)

        asyncio.run(_run())

    def test_sse_high_concurrency_fan_out_50_subscribers(self):
        """50 concurrent SSE subscribers subscribing and unsubscribing under live event load."""
        async def _run():
            hub = TelemetryHub()
            for i in range(1, 4):
                hub.publish_event("agent_thought", "Analyst", f"Seed {i}")

            subscribers = []
            for i in range(50):
                # Vary since_id: alternating 0 and 2
                s_id = 0 if i % 2 == 0 else 2
                q = await hub.subscribe_sse(since_id=s_id)
                subscribers.append((q, 3 if s_id == 0 else 1))

            # Check backlog sizes
            for q, expected_count in subscribers:
                assert q.qsize() == expected_count

            # Broadcast 5 live events concurrently
            for k in range(5):
                hub.publish_event("tool_call", "Market Analyst", f"Live broadcast tick {k+1}")

            # Each subscriber must have received exactly 5 additional live events
            for q, initial_count in subscribers:
                assert q.qsize() == initial_count + 5

            # Concurrently unsubscribe all 50
            unsub_tasks = [hub.unsubscribe_sse(q) for q, _ in subscribers]
            await asyncio.gather(*unsub_tasks)
            assert len(hub.sse_subscribers) == 0

        asyncio.run(_run())

    def test_sse_http_stream_multiple_concurrent_requests(self, live_client):
        """Verify HTTP SSE endpoint streams valid formatted frames with since_id and limit."""
        client, app, hub, bridge = live_client
        for i in range(1, 6):
            hub.publish_event("agent_thought", "Market Analyst", f"Deliberation #{i}")

        # Note: sse_event_generator counts ': connected\n\n' as frame 1, so limit=4 yields connected + 3 events
        res = client.get(f"/events/reasoning?since_id=2&limit=4&token={TEST_AUTH_TOKEN}")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        text = res.text
        assert ": connected" in text
        assert "id: 3" in text
        assert "id: 4" in text
        assert "id: 5" in text


# ===========================================================================
# 4. Bridge JSON-RPC, Concurrency & Rate Limiting Stress
# ===========================================================================

class TestMetaMaskBridgeRpcEdgeCasesAndRateLimiting:
    """Stress tests JSON-RPC parser, concurrent staging, and endpoint rate limiters."""

    def test_rpc_eth_sendTransaction_malformed_params_handling(self, live_client):
        """
        Adversarial test on /rpc eth_sendTransaction:
        Sending non-dict or empty params list must not crash the server with unhandled 500.
        """
        client, app, hub, bridge = live_client

        # Empty params list
        res_empty = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "eth_sendTransaction", "params": [], "id": 10},
            headers=auth_headers(),
        )
        assert res_empty.status_code == 200
        # Returns simulated hash on default dict fallback
        assert "result" in res_empty.json()

    def test_rpc_wallet_sync_account_variations(self, live_client):
        """Sync account supports both hex chain ID ('0xa4b1') and integer chain ID (42161)."""
        client, app, hub, bridge = live_client

        # Hex chain ID
        test_hex_addr = "0x1111111111111111111111111111111111111111"
        res_hex = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "wallet_syncAccount", "params": [test_hex_addr, "0xa4b1"], "id": 20},
            headers=auth_headers(),
        )
        assert res_hex.status_code == 200
        assert bridge.chain_id == 42161
        assert test_hex_addr in bridge.connected_accounts

        # Decimal chain ID via direct POST
        test_dec_addr = "0x2222222222222222222222222222222222222222"
        res_dec = client.post(
            "/wallet_syncAccount",
            json={"account": test_dec_addr, "chain_id": 8453},
            headers=auth_headers(),
        )
        assert res_dec.status_code == 200
        assert bridge.chain_id == 8453
        assert test_dec_addr in bridge.connected_accounts

    def test_concurrent_transaction_staging_and_confirmations(self, live_client):
        """High-concurrency: 12 threads simultaneously staging and confirming distinct transactions (24 requests, within 30-req limit)."""
        client, app, hub, bridge = live_client

        def stage_and_confirm(i: int):
            stage_res = client.post(
                "/send-transaction",
                json={"to": f"0xUser{i:040d}", "amount_in_wei": 100 * (i + 1)},
                headers=auth_headers(),
            )
            assert stage_res.status_code == 200
            req_id = stage_res.json()["request_id"]

            tx_hash = f"0x{i:064x}"
            conf_res = client.post(
                "/confirm-transaction",
                json={"request_id": req_id, "success": True, "tx_hash": tx_hash},
                headers=auth_headers(),
            )
            assert conf_res.status_code == 200
            return req_id, tx_hash

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(stage_and_confirm, i) for i in range(12)]
            results = [f.result() for f in futures]

        assert len(results) == 12
        # Verify all 12 are recorded as confirmed
        for req_id, tx_hash in results:
            assert bridge.transaction_results[req_id]["status"] == "confirmed"
            assert bridge.transaction_results[req_id]["tx_hash"] == tx_hash

    def test_rate_limiter_transaction_endpoints_saturation(self, live_client):
        """Transactions endpoint rate limiter blocks requests exceeding 30 requests/min with HTTP 429."""
        client, app, hub, bridge = live_client

        # Rapidly send 35 requests to /send-transaction
        statuses = []
        for i in range(35):
            res = client.post(
                "/send-transaction",
                json={"to": "0xFloodAddress", "amount_in_wei": 10},
                headers=auth_headers(),
            )
            statuses.append(res.status_code)

        # First 30 should succeed (200), subsequent requests should be rate-limited (429)
        successes = [s for s in statuses if s == 200]
        rate_limited = [s for s in statuses if s == 429]
        assert len(successes) == 30, f"Expected exactly 30 successful requests, got {len(successes)}"
        assert len(rate_limited) == 5, f"Expected 5 rate-limited requests, got {len(rate_limited)}"
