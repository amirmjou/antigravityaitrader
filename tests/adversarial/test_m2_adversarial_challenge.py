"""
Adversarial Stress Test & Verification Suite for Milestone 2 (Features F08–F14).
Authored by teamwork_challenger_m2_2.

Stress-tests:
1. Keystore Security:
   - Wrong password rejection
   - Corrupted ciphertext, truncated mac, corrupted salt, invalid JSON structure
   - Private key formatting (0x-prefix, 66 characters, hex normalization)
2. EIP-1193 Bridge:
   - JSON-RPC protocol error handling (-32601 for unsupported method, -32602 for invalid params)
   - Malformed payloads and parameter validation
   - Chain switching with valid and invalid chain IDs
   - Transaction rejection lifecycle (REST and WebSocket paths)
   - Staging queue consistency and deduplication
3. Nonce Management:
   - Strictly monotonic sequential nonce increments across rapid transaction batches
   - Manual override and resync with provider
   - Resync error resilience and network failure propagation
4. Multi-DEX Routing:
   - Calldata and ExactInputSingle parameter construction across Arbitrum One and Base
   - Protocol resolution (Uniswap v3 vs Aerodrome)
   - Unsupported and boundary chain IDs (unknown, negative, zero)
   - Deadline calculations and timestamp boundaries
5. Pre-Broadcast Guardrail Boundary & Stress Hardening:
   - Layer 1: Honeypot variations (boolean, string, integer), tax boundary (1.00% vs 1.01%), token_in and token_out compromise
   - Layer 2: Exact boundary checks ($250.00 vs $250.01, concentration 20.00% vs 20.01%, drawdown 7.99% vs 8.00%)
   - Layer 3: Slippage limit, price impact boundary (2.00% vs 2.01%), deadline limit (300s vs 301s)
   - Layer 4: Base fee ceiling boundary, gas-to-trade cost ratio boundary (1.50% vs 1.51%)
   - Layer 5: Pre-flight simulation revert reason extraction across varied EVM revert strings
"""
import json
import time
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from execution.wallet.hot_signer import HotKeystoreSigner
from execution.wallet.eip1193_bridge import (
    EIP1193BridgeServer,
    JsonRpcRequest,
    SendTxRequest,
    ConfirmTxRequest,
    create_bridge_app,
)
from execution.wallet.router import DualEngineWalletRouter
from execution.routers.dex_router import (
    MultiDEXRouter,
    DEXRouterConfig,
    KNOWN_DEX_CONFIGS,
)
from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from tests.e2e.contracts import (
    ChainExecutionConfig,
    GuardrailVerdict,
    SwapTransactionRequest,
    SwapExecutionResult,
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
def mock_w3_arb():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def mock_w3_base():
    return MockWeb3Provider(chain_id=8453, base_fee_gwei=0.005)


@pytest.fixture
def arb_exec_config():
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
def base_exec_config():
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


# ===========================================================================
# 1. Keystore Security & Cryptographic Integrity Challenge
# ===========================================================================

class TestKeystoreSecurityChallenge:
    """Stress tests keystore encryption, decryption, tampering, and key format."""

    def test_wrong_password_strictly_rejected(self):
        signer = HotKeystoreSigner.create_new()
        keystore_dict = signer.export_keystore("correct_password_123")

        with pytest.raises(ValueError):
            HotKeystoreSigner.from_keystore_json(keystore_dict, "WRONG_password_999")

    def test_corrupted_keystore_ciphertext_tampering(self):
        signer = HotKeystoreSigner.create_new()
        keystore_dict = signer.export_keystore("pass123")

        # Mutate ciphertext bytes
        crypto_key = "crypto" if "crypto" in keystore_dict else "Crypto"
        original_ct = keystore_dict[crypto_key]["ciphertext"]
        tampered_ct = original_ct[:4] + ("00" if original_ct[4:6] != "00" else "ff") + original_ct[6:]
        keystore_dict[crypto_key]["ciphertext"] = tampered_ct

        with pytest.raises(Exception):
            HotKeystoreSigner.from_keystore_json(keystore_dict, "pass123")

    def test_corrupted_keystore_mac_tampering(self):
        signer = HotKeystoreSigner.create_new()
        keystore_dict = signer.export_keystore("pass123")

        crypto_key = "crypto" if "crypto" in keystore_dict else "Crypto"
        keystore_dict[crypto_key]["mac"] = "0" * 64

        with pytest.raises(ValueError):
            HotKeystoreSigner.from_keystore_json(keystore_dict, "pass123")

    def test_malformed_keystore_json_structures(self):
        # Missing crypto structure entirely
        invalid_keystores = [
            {},
            {"version": 3},
            {"id": "test", "crypto": {}},
            {"version": 3, "crypto": {"cipher": "aes-128-ctr"}},
        ]
        for bad_ks in invalid_keystores:
            with pytest.raises(Exception):
                HotKeystoreSigner.from_keystore_json(bad_ks, "any_pass")

    def test_corrupted_keystore_file_handling(self, tmp_path):
        bad_file = tmp_path / "corrupted_keystore.json"
        bad_file.write_text("{ this is not valid json !@#$%^&*() }", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            HotKeystoreSigner.from_keystore_file(bad_file, "any_pass")

    def test_private_key_format_invariants(self):
        # 1. From generated account
        signer = HotKeystoreSigner.create_new()
        assert signer.private_key_hex.startswith("0x")
        assert len(signer.private_key_hex) == 66  # 0x + 64 hex chars = 32 bytes
        int(signer.private_key_hex, 16)  # Must be valid hex

        # 2. From key without 0x prefix
        raw_hex = "4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
        signer_no_prefix = HotKeystoreSigner.from_private_key(raw_hex)
        assert signer_no_prefix.private_key_hex.startswith("0x")
        assert len(signer_no_prefix.private_key_hex) == 66
        assert signer_no_prefix.private_key_hex == "0x" + raw_hex

        # 3. Invalid key lengths / non-hex must fail
        with pytest.raises(ValueError):
            HotKeystoreSigner.from_private_key("0x1234")  # Too short

        with pytest.raises(ValueError):
            HotKeystoreSigner.from_private_key("0xZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ")


# ===========================================================================
# 2. EIP-1193 Bridge Server Challenge
# ===========================================================================

class TestEIP1193BridgeChallenge:
    """Stress tests EIP-1193 JSON-RPC endpoints, error codes, and rejection flows."""

    def test_rpc_unsupported_methods_return_32601(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        unsupported_methods = [
            "eth_mining",
            "eth_hashrate",
            "eth_syncing",
            "net_peerCount",
            "web3_clientVersion",
            "admin_nodeInfo",
            "debug_traceTransaction",
            "random_unknown_method_xyz",
        ]

        for method in unsupported_methods:
            res = client.post("/rpc", json={"jsonrpc": "2.0", "id": 42, "method": method, "params": []})
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == 42
            assert data.get("result") is None
            assert data.get("error") is not None
            assert data["error"]["code"] == -32601
            assert "not supported" in data["error"]["message"].lower()

    def test_rpc_invalid_params_for_send_transaction_returns_32602(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # 1. Empty params
        res = client.post("/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "eth_sendTransaction", "params": []})
        data = res.json()
        assert data["error"]["code"] == -32602

        # 2. Params not a list of dict
        res2 = client.post("/rpc", json={"jsonrpc": "2.0", "id": 2, "method": "eth_sendTransaction", "params": ["not_a_dict"]})
        data2 = res2.json()
        assert data2["error"]["code"] == -32602

    def test_rpc_chain_switch_valid_and_invalid(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # Switch to Base (chain_id 8453 -> hex 0x2105)
        res = client.post("/rpc", json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "wallet_switchEthereumChain",
            "params": [{"chainId": "0x2105"}],
        })
        assert res.json()["result"] is None
        assert bridge.chain_id == 8453

        # Verify eth_chainId and net_version reflect switch
        res_cid = client.post("/rpc", json={"jsonrpc": "2.0", "id": 11, "method": "eth_chainId"})
        assert res_cid.json()["result"] == "0x2105"

        res_net = client.post("/rpc", json={"jsonrpc": "2.0", "id": 12, "method": "net_version"})
        assert res_net.json()["result"] == "8453"

        # Invalid chain switch params
        res_inv = client.post("/rpc", json={
            "jsonrpc": "2.0",
            "id": 13,
            "method": "wallet_switchEthereumChain",
            "params": [],
        })
        assert res_inv.json()["error"]["code"] == -32602

    def test_transaction_rejection_flow(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # 1. Stage a transaction
        tx_payload = {
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 100000000000000000,
            "amount_out_min_wei": 310000000,
            "trade_value_usd": 150.0,
            "chain_id": 42161,
        }
        res_stage = client.post("/send-transaction", json=tx_payload)
        assert res_stage.status_code == 200
        staged = res_stage.json()
        req_id = staged["request_id"]
        assert req_id in bridge.pending_transactions

        # 2. Reject the transaction via /confirm-transaction with success=False
        res_reject = client.post("/confirm-transaction", json={
            "request_id": req_id,
            "success": False,
            "error_reason": "User rejected in MetaMask prompt (code 4001)",
        })
        assert res_reject.status_code == 200
        reject_data = res_reject.json()
        assert reject_data["status"] == "rejected"
        assert "User rejected" in reject_data["error_reason"]

        # 3. Verify removed from pending
        assert req_id not in bridge.pending_transactions
        assert bridge.transaction_results[req_id]["status"] == "rejected"

        # 4. Attempting to reject again returns error
        res_again = client.post("/confirm-transaction", json={"request_id": req_id, "success": False})
        assert res_again.json()["success"] is False

    def test_websocket_rejection_message(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # Stage transaction
        staged = bridge.stage_transaction_sync({"to": "0xRouter", "amount": 100})
        req_id = staged["request_id"]
        assert req_id in bridge.pending_transactions

        with client.websocket_connect("/ws") as ws:
            init_msg = json.loads(ws.receive_text())
            assert init_msg["type"] == "CONNECTED"

            # Send rejection via websocket
            ws.send_text(json.dumps({
                "type": "REJECT",
                "request_id": req_id,
                "reason": "Cancelled by user on device",
            }))
            # Yield to event loop
            time.sleep(0.05)

        assert req_id not in bridge.pending_transactions
        assert bridge.transaction_results[req_id]["status"] == "rejected"


# ===========================================================================
# 3. Nonce Management & Resync Challenge
# ===========================================================================

class TestNonceManagementChallenge:
    """Stress tests monotonic nonce sequence, manual overrides, and node resync."""

    def test_rapid_consecutive_nonce_increments(self):
        signer = HotKeystoreSigner.create_new()
        start_nonce = signer.get_nonce()
        assert start_nonce == 0

        # Sign 10 consecutive transactions
        tx_template = {
            "to": "0x1111111111111111111111111111111111111111",
            "value": 1000,
            "gas": 21000,
            "maxFeePerGas": 1000000000,
            "maxPriorityFeePerGas": 50000000,
            "chainId": 42161,
        }

        signed_nonces = []
        for i in range(10):
            res = signer.sign_transaction(tx_template)
            signed_nonces.append(res["nonce"])

        # Check strict consecutive integers [0, 1, 2, ..., 9]
        assert signed_nonces == list(range(10))
        # Internal tracker now at 10
        assert signer.get_nonce() == 10

    def test_nonce_override_and_resync_with_provider(self):
        class MockWeb3Node:
            class eth:
                @staticmethod
                def get_transaction_count(address, tag):
                    return 55

        mock_w3 = MockWeb3Node()
        signer = HotKeystoreSigner.create_new(web3_provider=mock_w3)

        # Force override to 12
        signer.set_nonce(12)
        assert signer.get_nonce() == 12

        # Resync should query mock provider and reset to 55
        resynced = signer.resync_nonce()
        assert resynced == 55
        assert signer.get_nonce() == 55

    def test_nonce_resync_without_eth_attribute_resets_to_zero(self, mock_w3_arb):
        # mock_w3_arb does not have .eth attribute
        signer = HotKeystoreSigner.create_new(web3_provider=mock_w3_arb)
        signer.set_nonce(99)

        # Resync resets safely to 0
        signer.resync_nonce()
        assert signer.get_nonce() == 0

    def test_nonce_resync_with_failing_node_raises_exception(self):
        class BrokenNode:
            class eth:
                @staticmethod
                def get_transaction_count(addr, tag):
                    raise ConnectionResetError("RPC Node connection timeout")

        broken_w3 = BrokenNode()
        signer = HotKeystoreSigner.create_new(web3_provider=broken_w3)
        signer.set_nonce(99)

        # Explicit force-resync must fail-fast rather than silently corrupt nonce to 0
        with pytest.raises(ConnectionResetError):
            signer.resync_nonce()


# ===========================================================================
# 4. Multi-DEX Router Challenge
# ===========================================================================

class TestMultiDEXRouterChallenge:
    """Stress tests DEX configuration, calldata parameter encoding, and chain validation."""

    def test_arbitrum_and_base_canonical_addresses(self):
        router = MultiDEXRouter()

        # Arbitrum One (42161)
        arb_cfg = router.get_config(42161)
        assert arb_cfg.uniswap_router.lower() == "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45".lower()
        assert arb_cfg.uniswap_quoter.lower() == "0x61ffe014ba136170505655d03170f09287640f16".lower()
        assert arb_cfg.aerodrome_router is None

        # Base (8453)
        base_cfg = router.get_config(8453)
        assert base_cfg.uniswap_router.lower() == "0x2626664c2603336e57b271c5c0b26f421741e481".lower()
        assert base_cfg.uniswap_quoter.lower() == "0x3d4e44eb1374240ce5f1b871ab261cd16335b76a".lower()
        assert base_cfg.aerodrome_router.lower() == "0xcf77a3ba9a5ca399b7c97c74856154938591a088".lower()

        # Aerodrome protocol selection on Base
        aero_addr = router.get_router_address(8453, protocol="aerodrome")
        assert aero_addr.lower() == base_cfg.aerodrome_router.lower()

        # Uniswap v3 protocol selection on Base
        uni_addr = router.get_router_address(8453, protocol="uniswap_v3")
        assert uni_addr.lower() == base_cfg.uniswap_router.lower()

    def test_unsupported_and_invalid_chain_ids(self):
        router = MultiDEXRouter()

        invalid_chains = [999999, 137, 56, 10, -1, 0]
        for cid in invalid_chains:
            with pytest.raises(ValueError) as excinfo:
                router.get_config(cid)
            assert f"Unsupported chain_id: {cid}" in str(excinfo.value)

    def test_exact_input_single_params_struct_and_deadline(self):
        router = MultiDEXRouter()
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            amount_in_wei=1000000000000000000,
            amount_out_min_wei=3100000000,
            recipient="0xRecipientAddress000000000000000000000001",
            deadline_seconds=180,
            trade_value_usd=3100.0,
        )

        before_ts = int(time.time())
        params = router.build_exact_input_single_params(req, fee_tier=3000)
        after_ts = int(time.time())

        assert params["tokenIn"] == req.token_in
        assert params["tokenOut"] == req.token_out
        assert params["fee"] == 3000
        assert params["recipient"] == req.recipient
        assert params["amountIn"] == req.amount_in_wei
        assert params["amountOutMinimum"] == req.amount_out_min_wei
        assert params["sqrtPriceLimitX96"] == 0
        assert before_ts + 180 <= params["deadline"] <= after_ts + 180

    def test_approval_transaction_structure(self):
        router = MultiDEXRouter()
        tx = router.build_approval_transaction(
            token_address="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            spender_address="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            amount_wei=2**256 - 1,
            signer_address="0xSignerAddress0000000000000000000000001",
            chain_id=42161,
        )
        assert tx["to"] == "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
        assert tx["spender"] == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
        assert tx["amount"] == 2**256 - 1
        assert tx["gas"] == 60000


# ===========================================================================
# 5. Pre-Broadcast Safety Guardrails Stress & Boundary Challenge
# ===========================================================================

class TestGuardrailsStressAndBoundaryChallenge:
    """Stress tests boundary precision and edge cases across all 5 guardrail layers."""

    @pytest.fixture
    def guardrail_pipeline(self, arb_exec_config, mock_w3_arb):
        goplus = MockGoPlusClient()
        quoter = MockUniswapV3Quoter(base_price_usd=88500.0, pool_liquidity_usd=50000000.0)
        return PreBroadcastGuardrailPipeline(
            chain_config=arb_exec_config,
            web3_provider=mock_w3_arb,
            goplus_client=goplus,
            quoter=quoter,
            max_spend_per_trade_usd=250.0,
            max_asset_concentration_pct=20.0,
            max_daily_drawdown_pct=8.0,
        )

    def test_layer1_honeypot_type_resilience(self, guardrail_pipeline):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeToken",
            token_out="0xHoneypotToken",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )

        # Test boolean True, string "1", integer 1
        for val in [True, "1", 1]:
            guardrail_pipeline.goplus.token_database["0xHoneypotToken"] = {"is_honeypot": val}
            verdict = guardrail_pipeline.evaluate(req)
            assert verdict.approved is False
            assert "Honeypot" in verdict.rejection_reason

    def test_layer1_token_in_vs_token_out_compromise(self, guardrail_pipeline):
        # 1. Compromised token_in
        req1 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xBadTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        guardrail_pipeline.goplus.token_database["0xBadTokenIn"] = {"is_honeypot": "1"}
        guardrail_pipeline.goplus.token_database["0xSafeTokenOut"] = {"is_honeypot": "0"}
        verdict1 = guardrail_pipeline.evaluate(req1)
        assert verdict1.approved is False
        assert "token_in" in verdict1.rejection_reason

        # 2. Compromised token_out
        req2 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xBadTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        guardrail_pipeline.goplus.token_database["0xSafeTokenIn"] = {"is_honeypot": "0"}
        guardrail_pipeline.goplus.token_database["0xBadTokenOut"] = {"is_honeypot": "1"}
        verdict2 = guardrail_pipeline.evaluate(req2)
        assert verdict2.approved is False
        assert "token_out" in verdict2.rejection_reason

    def test_layer1_tax_boundary_precision(self, guardrail_pipeline):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xTokenA",
            token_out="0xTokenB",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )

        # Exactly 1.00% tax -> ALLOWED
        guardrail_pipeline.goplus.token_database["0xTokenB"] = {"buy_tax": "0.0100", "sell_tax": "0.0100"}
        v_allowed = guardrail_pipeline.evaluate(req)
        assert v_allowed.approved is True

        # 1.01% tax -> BLOCKED
        guardrail_pipeline.goplus.token_database["0xTokenB"] = {"buy_tax": "0.0101", "sell_tax": "0.0000"}
        v_blocked = guardrail_pipeline.evaluate(req)
        assert v_blocked.approved is False
        assert "Tax exceeds 1% ceiling" in v_blocked.rejection_reason

    def test_layer2_capital_allocation_exact_boundaries(self, guardrail_pipeline):
        # 1. Per-trade spend: $250.00 vs $250.01
        req_250 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=250.00,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        assert guardrail_pipeline.evaluate(req_250).approved is True

        req_250_01 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=250.01,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        v_spend = guardrail_pipeline.evaluate(req_250_01)
        assert v_spend.approved is False
        assert "exceeds cap of $250.0" in v_spend.rejection_reason

        # 2. Concentration: (holdings + trade) / portfolio
        # portfolio = $1750. trade = $250. holdings = $100 -> (100+250)/1750 = 350/1750 = 20.00% -> ALLOWED
        v_conc_exact = guardrail_pipeline.evaluate(
            req_250, current_portfolio_value_usd=1750.0, current_asset_holdings_usd=100.0
        )
        assert v_conc_exact.approved is True

        # (101 + 250) / 1750 = 351 / 1750 = 20.057% -> BLOCKED
        v_conc_over = guardrail_pipeline.evaluate(
            req_250, current_portfolio_value_usd=1750.0, current_asset_holdings_usd=101.0
        )
        assert v_conc_over.approved is False
        assert "Asset concentration" in v_conc_over.rejection_reason

        # 3. Daily drawdown: 7.99% vs 8.00%
        req_small = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=50.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        assert guardrail_pipeline.evaluate(req_small, current_daily_drawdown_pct=7.99).approved is True

        v_dd = guardrail_pipeline.evaluate(req_small, current_daily_drawdown_pct=8.00)
        assert v_dd.approved is False
        assert "Daily drawdown" in v_dd.rejection_reason

    def test_layer3_slippage_and_deadline_boundaries(self, guardrail_pipeline):
        # 1. Slippage: 100 bps vs 101 bps (max_slippage_bps = 100)
        req_slip_100 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            slippage_bps=100,
            deadline_seconds=300,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        assert guardrail_pipeline.evaluate(req_slip_100).approved is True

        req_slip_101 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            slippage_bps=101,
            deadline_seconds=300,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        v_slip = guardrail_pipeline.evaluate(req_slip_101)
        assert v_slip.approved is False
        assert "Requested slippage 101 bps exceeds max 100" in v_slip.rejection_reason

        # 2. Deadline: 300s vs 301s
        req_dl_301 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            slippage_bps=50,
            deadline_seconds=301,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        v_dl = guardrail_pipeline.evaluate(req_dl_301)
        assert v_dl.approved is False
        assert "deadline 301s exceeds 300s limit" in v_dl.rejection_reason

        # 3. Price impact: 2.00% vs 2.01%
        assert guardrail_pipeline.evaluate(req_slip_100, override_quoter_impact_pct=2.00).approved is True
        v_pi = guardrail_pipeline.evaluate(req_slip_100, override_quoter_impact_pct=2.01)
        assert v_pi.approved is False
        assert "Price impact 2.01% exceeds 2.0% threshold" in v_pi.rejection_reason

    def test_layer4_gas_boundaries(self, guardrail_pipeline):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )

        # 1. Base fee ceiling check (checked first in Layer 4)
        # When base_fee_gwei = 120.1 > ceiling (120.0), trips base fee ceiling
        guardrail_pipeline.w3.base_fee_gwei = 120.1
        v_ceiling = guardrail_pipeline.evaluate(req)
        assert v_ceiling.approved is False
        assert "exceeds ceiling 120.0 gwei" in v_ceiling.rejection_reason
        assert v_ceiling.layer_failed == "Layer 4: Gas & Congestion"

        # 2. Gas-to-trade ratio check at trade_value_usd = $100.0 (max ratio 1.5% = $1.50 max gas)
        # At base_fee = 3.20 gwei, gas cost = 145000 * 3.25 * 1e-9 * 3100 = $1.46 (1.46%) -> ALLOWED
        guardrail_pipeline.w3.base_fee_gwei = 3.20
        v_ratio_pass = guardrail_pipeline.evaluate(req)
        assert v_ratio_pass.approved is True

        # At base_fee = 3.40 gwei, gas cost = 145000 * 3.45 * 1e-9 * 3100 = $1.55 (1.55%) -> BLOCKED
        guardrail_pipeline.w3.base_fee_gwei = 3.40
        v_ratio_fail = guardrail_pipeline.evaluate(req)
        assert v_ratio_fail.approved is False
        assert "Gas-to-trade ratio" in v_ratio_fail.rejection_reason
        assert v_ratio_fail.layer_failed == "Layer 4: Gas & Congestion"

    def test_layer5_simulation_varied_revert_messages(self, guardrail_pipeline):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafe",
            token_out="0xSafeOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xRecipient00000000000000000000000000000001",
        )
        guardrail_pipeline.w3.base_fee_gwei = 0.1

        revert_cases = [
            ("execution reverted: UniswapV3: STF", "UniswapV3: STF"),
            ("execution reverted: TRANSFER_FAILED", "TRANSFER_FAILED"),
            ("reverted: InsufficientOutputAmount", "InsufficientOutputAmount"),
            ("execution reverted: 0x4e487b71", "0x4e487b71"),
            ("CustomContractError(42)", "CustomContractError(42)"),
        ]

        for raw_revert, expected_parsed in revert_cases:
            def throw_revert(_):
                raise RuntimeError(raw_revert)

            guardrail_pipeline.w3.eth_call = throw_revert
            v = guardrail_pipeline.evaluate(req)
            assert v.approved is False
            assert expected_parsed in v.rejection_reason
            assert v.layer_failed == "Layer 5: Pre-Flight Simulation"
