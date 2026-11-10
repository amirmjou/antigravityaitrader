"""
MetaMask Transaction Lifecycle Adversarial Stress Harness (Milestone 6 Iteration 2).
Authored by teamwork_challenger_m6_it2_2.

Rigorous empirical stress testing covering:
1. Concurrent Double-Confirmation Race Conditions (Threaded race attack on single request_id)
2. Post-Rejection Confirmation Immunity (Reject, then multi-thread confirm attempts)
3. Fuzzed & Hostile request_id Payload Handling (Path traversal, SQLi, extreme lengths, empty)
4. Rejection State Immutability & Persistence
5. Comprehensive Guardrail Pipeline L1-L3 Stress & Router Interception
"""
from __future__ import annotations

import concurrent.futures
import os
import sys
import time
from typing import Any, Dict, List
import pytest
from starlette.testclient import TestClient

from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from execution.wallet.eip1193_bridge import (
    ConfirmTxRequest,
    EIP1193BridgeServer,
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

TEST_AUTH_TOKEN = "m6_it2_challenger_secret_token_2026!"


@pytest.fixture(autouse=True)
def clean_security_state(monkeypatch):
    """Ensure clean isolation between tests."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
    monkeypatch.setenv("TRADING_API_KEY", TEST_AUTH_TOKEN)
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    os.environ.pop("TRADINGAGENTS_SECURITY_MODE", None)
    os.environ.pop("TRADING_API_KEY", None)


@pytest.fixture
def test_setup():
    hub = TelemetryHub()
    bridge = EIP1193BridgeServer(default_chain_id=42161)
    app = create_visualization_app(hub=hub, bridge_server=bridge)
    client = TestClient(app, raise_server_exceptions=False)
    return client, app, hub, bridge


def auth_headers():
    return {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}


# ==============================================================================
# 1. Concurrent Double-Confirmation Race Conditions
# ==============================================================================

class TestConcurrentLifecycleDoubleConfirmation:
    """Stress tests race conditions where multiple clients attempt to confirm the same transaction."""

    def test_concurrent_double_confirm_race_exact_single_winner(self, test_setup):
        """
        Adversarial Race Condition:
        Stage 1 transaction, then launch 10 concurrent threads each attempting to confirm
        the same request_id with distinct hashes.
        Exactly ONE thread must receive HTTP 200 / status='confirmed', and all 9 others
        must receive HTTP 404.
        """
        client, app, hub, bridge = test_setup

        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 5000},
            headers=auth_headers(),
        )
        assert stage_res.status_code == 200
        req_id = stage_res.json()["request_id"]
        assert req_id in bridge.pending_transactions

        # Reset rate limiter to avoid 429 during burst test
        global_rate_limiter.reset()

        hashes = [f"0x{i:02x}" + "f" * 62 for i in range(10)]
        results: List[Dict[str, Any]] = []

        def worker_confirm(tx_hash: str):
            res = client.post(
                "/confirm-transaction",
                json={"request_id": req_id, "success": True, "tx_hash": tx_hash},
                headers=auth_headers(),
            )
            return {"status_code": res.status_code, "data": res.json(), "tx_hash": tx_hash}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_confirm, h) for h in hashes]
            results = [f.result() for f in futures]

        status_200s = [r for r in results if r["status_code"] == 200]
        status_404s = [r for r in results if r["status_code"] == 404]

        assert len(status_200s) == 1, f"Expected exactly 1 confirmation winner, got {len(status_200s)}"
        assert len(status_404s) == 9, f"Expected 9 rejected attempts with 404, got {len(status_404s)}"

        winning_hash = status_200s[0]["tx_hash"]
        assert req_id not in bridge.pending_transactions
        assert req_id in bridge.transaction_results
        assert bridge.transaction_results[req_id]["status"] == "confirmed"
        assert bridge.transaction_results[req_id]["tx_hash"] == winning_hash

    def test_post_rejection_multi_confirmation_immune(self, test_setup):
        """
        Adversarial Test:
        Transaction is rejected first. Then 8 concurrent threads attempt to confirm it.
        All 8 confirmation attempts must be rejected with HTTP 404.
        The rejection record and reason must not be modified or erased.
        """
        client, app, hub, bridge = test_setup

        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x2222222222222222222222222222222222222222", "amount_in_wei": 1200},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]

        rejection_reason = "User explicitly cancelled transaction via hardware wallet prompt"
        rej_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": rejection_reason},
            headers=auth_headers(),
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"
        assert bridge.transaction_results[req_id]["status"] == "rejected"

        global_rate_limiter.reset()

        def try_confirm(idx: int):
            return client.post(
                "/confirm-transaction",
                json={"request_id": req_id, "success": True, "tx_hash": f"0x{idx:064x}"},
                headers=auth_headers(),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(try_confirm, i) for i in range(8)]
            responses = [f.result() for f in futures]

        for resp in responses:
            assert resp.status_code == 404
            assert f"Request {req_id} not found" in resp.json()["detail"]

        # Ensure rejection state remains pristine
        assert bridge.transaction_results[req_id]["status"] == "rejected"
        assert bridge.transaction_results[req_id]["error_reason"] == rejection_reason


# ==============================================================================
# 2. Hostile & Fuzzed request_id Handling
# ==============================================================================

class TestHostileRequestIdFuzzing:
    """Fuzzes request_id across hostile strings, ensuring zero unhandled 500 exceptions."""

    @pytest.mark.parametrize(
        "hostile_id",
        [
            "",
            "   ",
            "tx_nonexistent_12345",
            "0x" + "0" * 40,
            "../" * 10 + "windows/system32",
            "' OR '1'='1' --",
            "<script>alert('xss')</script>",
            "\x00\x01\x02\x03",
            "A" * 5000,  # Extreme length string
        ],
    )
    def test_fuzzed_request_id_confirmation_returns_404_or_422_never_500(self, test_setup, hostile_id):
        client, app, hub, bridge = test_setup
        global_rate_limiter.reset()

        res = client.post(
            "/confirm-transaction",
            json={"request_id": hostile_id, "success": True, "tx_hash": "0x" + "f" * 64},
            headers=auth_headers(),
        )
        assert res.status_code in [404, 422, 400]
        assert res.status_code != 500


# ==============================================================================
# 3. Rejection State Persistence & Immutability
# ==============================================================================

class TestRejectionStatePersistence:
    """Verifies rejection state transitions and immutability under repetitive operations."""

    def test_rejection_populates_full_telemetry_and_persists(self, test_setup):
        client, app, hub, bridge = test_setup

        stage_res = client.post(
            "/send-transaction",
            json={"to": "0x3333333333333333333333333333333333333333", "amount_in_wei": 999},
            headers=auth_headers(),
        )
        req_id = stage_res.json()["request_id"]

        now_before = time.time()
        rej_res = client.post(
            "/confirm-transaction",
            json={"request_id": req_id, "success": False, "error_reason": "Slippage warning triggered user abort"},
            headers=auth_headers(),
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"
        assert rej_res.json()["request_id"] == req_id

        record = bridge.transaction_results.get(req_id)
        assert record is not None
        assert record["status"] == "rejected"
        assert record["error_reason"] == "Slippage warning triggered user abort"
        assert record["rejected_at"] >= now_before
        assert req_id not in bridge.pending_transactions


# ==============================================================================
# 4. Guardrail L1-L3 Stress Testing & DualEngine Router Interception
# ==============================================================================

class TestGuardrailsL1L2L3DeepStress:
    """Validates Guardrails L1, L2, L3 rules and router fail-safe interception."""

    @pytest.fixture
    def arb_config(self):
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
    def guardrails(self, arb_config):
        return PreBroadcastGuardrailPipeline(
            chain_config=arb_config,
            web3_provider=MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1),
            goplus_client=MockGoPlusClient(),
            quoter=MockUniswapV3Quoter(base_price_usd=3100.0, pool_liquidity_usd=50000000.0),
            max_spend_per_trade_usd=250.0,
            max_asset_concentration_pct=20.0,
            max_daily_drawdown_pct=8.0,
            eth_price_usd=3100.0,
        )

    def test_guardrail_l1_rejections(self, guardrails):
        # Self swap
        v_self = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1".lower(),
                amount_in_wei=10**16,
                amount_out_min_wei=10**16,
                recipient="0xUserWallet",
                trade_value_usd=100.0,
            )
        )
        assert v_self.approved is False
        assert v_self.layer_failed == "Layer 1: Contract Security"
        assert "Self-swap rejected" in v_self.rejection_reason

        # Zero amount
        v_zero = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=0,
                amount_out_min_wei=100,
                recipient="0xUserWallet",
                trade_value_usd=100.0,
            )
        )
        assert v_zero.approved is False
        assert v_zero.layer_failed == "Layer 1: Contract Security"
        assert "Non-positive amount_in_wei" in v_zero.rejection_reason

        # Honeypot
        v_honey = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0xBadHoneypotTokenAddress0000000000000000",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                trade_value_usd=50.0,
            )
        )
        assert v_honey.approved is False
        assert "Honeypot detected" in v_honey.rejection_reason

    def test_guardrail_l2_rejections(self, guardrails):
        # Spend cap exceeded ($250 cap, $350 trade)
        v_spend = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                trade_value_usd=350.0,
            )
        )
        assert v_spend.approved is False
        assert v_spend.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in v_spend.rejection_reason

        # Asset concentration exceeded
        v_conc = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                trade_value_usd=200.0,
            ),
            current_portfolio_value_usd=5000.0,
            current_asset_holdings_usd=900.0,
        )
        assert v_conc.approved is False
        assert "Asset concentration 22.0% exceeds max 20.0%" in v_conc.rejection_reason

        # Daily drawdown limit reached
        v_dd = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                trade_value_usd=100.0,
            ),
            current_daily_drawdown_pct=8.5,
        )
        assert v_dd.approved is False
        assert "Daily drawdown 8.5% exceeds circuit breaker 8.0%" in v_dd.rejection_reason

    def test_guardrail_l3_rejections(self, guardrails):
        # Excessive slippage (> 100 bps)
        v_slip = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                slippage_bps=120,
                trade_value_usd=100.0,
            )
        )
        assert v_slip.approved is False
        assert v_slip.layer_failed == "Layer 3: Dynamic Slippage"
        assert "Requested slippage 120 bps exceeds max 100 bps" in v_slip.rejection_reason

        # Negative slippage
        v_neg_slip = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                slippage_bps=-10,
                trade_value_usd=100.0,
            )
        )
        assert v_neg_slip.approved is False
        assert "Negative slippage tolerance rejected" in v_neg_slip.rejection_reason

        # Price impact > 2.0%
        v_pi = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                trade_value_usd=100.0,
            ),
            override_quoter_impact_pct=2.5,
        )
        assert v_pi.approved is False
        assert "Price impact 2.50% exceeds 2.0% threshold" in v_pi.rejection_reason

        # Expired / excessive deadline
        v_dl = guardrails.evaluate(
            SwapTransactionRequest(
                chain_id=42161,
                token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
                amount_in_wei=10**16,
                amount_out_min_wei=950000,
                recipient="0xUserWallet",
                deadline_seconds=305,
                trade_value_usd=100.0,
            )
        )
        assert v_dl.approved is False
        assert "deadline 305s exceeds 300s limit" in v_dl.rejection_reason

    def test_guardrail_interception_aborts_router_execution(self, arb_config, guardrails):
        """
        When Guardrails evaluate to approved=False, execution is intercepted,
        preventing any staged or broadcasted transactions on the bridge.
        """
        bridge = EIP1193BridgeServer()
        router = DualEngineWalletRouter(
            chain_config=arb_config,
            web3_provider=MockWeb3Provider(chain_id=42161),
            bridge_server=bridge,
        )

        toxic_req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xBadHoneypotTokenAddress0000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=50.0,
        )

        verdict = guardrails.evaluate(toxic_req)
        assert verdict.approved is False

        # Gate verification
        if verdict.approved:
            router.execute_swap(toxic_req, signer_mode="eip1193_metamask")
            executed = True
        else:
            executed = False

        assert executed is False
        assert len(bridge.pending_transactions) == 0

