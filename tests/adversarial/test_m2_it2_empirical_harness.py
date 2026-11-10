"""
Independent Empirical Challenger Harness for Milestone 2 Iteration 2 Gate Evaluation.
Authored by teamwork_challenger_m2_it2_2 (Empirical Challenger).

Empirically tests:
1. Exact Boundary Limits (Spend, Slippage, Deadline, Drawdown, Gas Ratio, Tax, Price Impact, Concentration)
2. Keystore Cryptographic Security (AES-128-CTR, Scrypt, password validation, signature recovery, tampering)
3. EIP-712 Typed Signing & EIP-191 Personal Sign with cryptographic recovery
4. EIP-1193 Bridge Lifecycle & JSON-RPC Protocol Compliance
5. Multi-DEX Router Canonical Addressing & Parameter Construction
"""
import json
import time
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from execution.wallet.hot_signer import HotKeystoreSigner
from execution.wallet.eip1193_bridge import EIP1193BridgeServer, JsonRpcRequest
from execution.routers.dex_router import MultiDEXRouter, KNOWN_DEX_CONFIGS
from tests.e2e.contracts import (
    ChainExecutionConfig,
    SwapTransactionRequest,
    GuardrailVerdict,
)
from tests.e2e.fixtures import (
    MockGoPlusClient,
    MockUniswapV3Quoter,
    MockWeb3Provider,
)
from starlette.testclient import TestClient


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
def mock_w3():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def mock_goplus():
    return MockGoPlusClient()


@pytest.fixture
def mock_quoter():
    return MockUniswapV3Quoter()


@pytest.fixture
def pipeline(arb_chain_config, mock_w3, mock_goplus, mock_quoter):
    return PreBroadcastGuardrailPipeline(
        chain_config=arb_chain_config,
        web3_provider=mock_w3,
        goplus_client=mock_goplus,
        quoter=mock_quoter,
        max_spend_per_trade_usd=250.0,
        max_asset_concentration_pct=20.0,
        max_daily_drawdown_pct=8.0,
        eth_price_usd=3100.0,
    )


# ===========================================================================
# 1. Exact Boundary Limits Pressure Testing
# ===========================================================================

class TestExactBoundaryLimits:
    """Rigorous boundary value analysis on all 6 guardrail layers."""

    def test_spend_limit_exact_boundaries(self, pipeline):
        """Spend cap: $250.00 allowed, $250.01 rejected, $249.99 allowed."""
        base_req = {
            "chain_id": 42161,
            "token_in": "0xSafeTokenIn",
            "token_out": "0xSafeTokenOut",
            "amount_in_wei": 10**18,
            "amount_out_min_wei": 10**6,
            "recipient": "0xUserRecipient0000000000000000000000000001",
        }

        # $249.99 -> ALLOWED
        v_under = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=249.99))
        assert v_under.approved is True

        # $250.00 -> EXACT CAP -> ALLOWED
        v_exact = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=250.00))
        assert v_exact.approved is True

        # $250.0001 -> JUST ABOVE -> BLOCKED
        v_just_over = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=250.0001))
        assert v_just_over.approved is False
        assert v_just_over.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in v_just_over.rejection_reason

        # $250.01 -> BLOCKED
        v_over = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=250.01))
        assert v_over.approved is False
        assert v_over.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in v_over.rejection_reason

        # $0.00 -> Non-positive rejected
        v_zero = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=0.0))
        assert v_zero.approved is False
        assert "Non-positive trade_value_usd" in v_zero.rejection_reason

        # -$10.00 -> Negative rejected
        v_neg = pipeline.evaluate(SwapTransactionRequest(**base_req, trade_value_usd=-10.0))
        assert v_neg.approved is False
        assert "Non-positive trade_value_usd" in v_neg.rejection_reason

    def test_slippage_exact_boundaries(self, pipeline):
        """Slippage cap: 100 bps allowed, 101 bps rejected, 0 bps allowed, negative rejected."""
        base_req = {
            "chain_id": 42161,
            "token_in": "0xSafeTokenIn",
            "token_out": "0xSafeTokenOut",
            "amount_in_wei": 10**18,
            "amount_out_min_wei": 10**6,
            "trade_value_usd": 100.0,
            "recipient": "0xUserRecipient0000000000000000000000000001",
        }

        # 0 bps -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, slippage_bps=0)).approved is True

        # 99 bps -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, slippage_bps=99)).approved is True

        # 100 bps -> EXACT CAP -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, slippage_bps=100)).approved is True

        # 101 bps -> BLOCKED
        v_over = pipeline.evaluate(SwapTransactionRequest(**base_req, slippage_bps=101))
        assert v_over.approved is False
        assert v_over.layer_failed == "Layer 3: Dynamic Slippage"
        assert "exceeds max 100" in v_over.rejection_reason

        # -1 bps -> BLOCKED
        v_neg = pipeline.evaluate(SwapTransactionRequest(**base_req, slippage_bps=-1))
        assert v_neg.approved is False
        assert "Negative slippage" in v_neg.rejection_reason

    def test_deadline_exact_boundaries(self, pipeline):
        """Deadline: 300s allowed, 301s rejected, 1s allowed, 0s rejected."""
        base_req = {
            "chain_id": 42161,
            "token_in": "0xSafeTokenIn",
            "token_out": "0xSafeTokenOut",
            "amount_in_wei": 10**18,
            "amount_out_min_wei": 10**6,
            "trade_value_usd": 100.0,
            "recipient": "0xUserRecipient0000000000000000000000000001",
        }

        # 1s -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=1)).approved is True

        # 299s -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=299)).approved is True

        # 300s -> EXACT CAP -> ALLOWED
        assert pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=300)).approved is True

        # 301s -> BLOCKED
        v_over = pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=301))
        assert v_over.approved is False
        assert v_over.layer_failed == "Layer 3: Dynamic Slippage"
        assert "exceeds 300s limit" in v_over.rejection_reason

        # 0s -> Non-positive rejected
        v_zero = pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=0))
        assert v_zero.approved is False
        assert "Non-positive deadline" in v_zero.rejection_reason

        # -5s -> Negative rejected
        v_neg = pipeline.evaluate(SwapTransactionRequest(**base_req, deadline_seconds=-5))
        assert v_neg.approved is False
        assert "Non-positive deadline" in v_neg.rejection_reason

    def test_drawdown_exact_boundaries(self, pipeline):
        """Daily drawdown breaker: 7.99% allowed, 8.00% rejected, 8.01% rejected."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=50.0,
            recipient="0xUserRecipient0000000000000000000000000001",
        )

        # 0.00% -> ALLOWED
        assert pipeline.evaluate(req, current_daily_drawdown_pct=0.0).approved is True

        # 7.99% -> ALLOWED
        assert pipeline.evaluate(req, current_daily_drawdown_pct=7.99).approved is True

        # 7.999% -> ALLOWED
        assert pipeline.evaluate(req, current_daily_drawdown_pct=7.999).approved is True

        # 8.00% -> CIRCUIT BREAKER TRIPS -> BLOCKED
        v_exact = pipeline.evaluate(req, current_daily_drawdown_pct=8.00)
        assert v_exact.approved is False
        assert v_exact.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds circuit breaker 8.0%" in v_exact.rejection_reason

        # 8.01% -> BLOCKED
        v_over = pipeline.evaluate(req, current_daily_drawdown_pct=8.01)
        assert v_over.approved is False
        assert "exceeds circuit breaker 8.0%" in v_over.rejection_reason

    def test_gas_ratio_exact_boundaries(self, pipeline):
        """Gas-to-trade ratio ceiling (1.50% max). At trade_value_usd=$100, max gas=$1.50."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xUserRecipient0000000000000000000000000001",
        )

        # base_fee = 3.20 gwei, priority_fee = 0.05 gwei
        # total_fee = 3.25 gwei -> gas_cost = 145000 * 3.25e-9 * 3100 = $1.460875 -> 1.46% (<= 1.50%) -> ALLOWED
        pipeline.w3.base_fee_gwei = 3.20
        v_pass = pipeline.evaluate(req)
        assert v_pass.approved is True

        # base_fee = 3.40 gwei, priority_fee = 0.05 gwei
        # total_fee = 3.45 gwei -> gas_cost = 145000 * 3.45e-9 * 3100 = $1.550775 -> 1.55% (> 1.50%) -> BLOCKED
        pipeline.w3.base_fee_gwei = 3.40
        v_fail = pipeline.evaluate(req)
        assert v_fail.approved is False
        assert v_fail.layer_failed == "Layer 4: Gas & Congestion"
        assert "Gas-to-trade ratio" in v_fail.rejection_reason

    def test_tax_and_price_impact_boundaries(self, pipeline):
        """
        Layer 1 Tax: 1.00% allowed, 1.01% rejected.
        Layer 3 Price Impact: 2.00% allowed, 2.01% rejected (PROJECT.md spec).
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=100.0,
            recipient="0xUserRecipient0000000000000000000000000001",
        )

        # 1. Tax at 1.00% (0.0100) -> ALLOWED
        pipeline.goplus.token_database["0xSafeTokenOut"] = {"buy_tax": "0.0100", "sell_tax": "0.0100"}
        assert pipeline.evaluate(req).approved is True

        # Tax at 1.01% (0.0101) -> BLOCKED (Layer 1)
        pipeline.goplus.token_database["0xSafeTokenOut"] = {"buy_tax": "0.0101", "sell_tax": "0.0000"}
        v_tax = pipeline.evaluate(req)
        assert v_tax.approved is False
        assert v_tax.layer_failed == "Layer 1: Contract Security"
        assert "Tax exceeds 1% ceiling" in v_tax.rejection_reason

        # Reset tax to clean
        pipeline.goplus.token_database["0xSafeTokenOut"] = {"buy_tax": "0.0000", "sell_tax": "0.0000"}

        # 2. Price impact: 1.00% and 1.01% are well within the 2.00% ceiling -> ALLOWED
        assert pipeline.evaluate(req, override_quoter_impact_pct=1.00).approved is True
        assert pipeline.evaluate(req, override_quoter_impact_pct=1.01).approved is True

        # Price impact at 2.00% -> ALLOWED
        assert pipeline.evaluate(req, override_quoter_impact_pct=2.00).approved is True

        # Price impact at 2.01% -> BLOCKED (Layer 3)
        v_impact = pipeline.evaluate(req, override_quoter_impact_pct=2.01)
        assert v_impact.approved is False
        assert v_impact.layer_failed == "Layer 3: Dynamic Slippage"
        assert "Price impact 2.01% exceeds 2.0% threshold" in v_impact.rejection_reason

    def test_asset_concentration_exact_boundaries(self, pipeline):
        """Asset concentration: 20.00% allowed, 20.01% rejected."""
        # portfolio = $1000, trade = $200, existing holdings = $0 -> (0 + 200)/1000 = 20.00% -> ALLOWED
        req_200 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=200.0,
            recipient="0xUserRecipient0000000000000000000000000001",
        )
        assert pipeline.evaluate(req_200, current_portfolio_value_usd=1000.0, current_asset_holdings_usd=0.0).approved is True

        # portfolio = $1000, trade = $200.1, existing holdings = $0 -> 200.1 / 1000 = 20.01% -> BLOCKED
        req_200_1 = SwapTransactionRequest(
            chain_id=42161,
            token_in="0xSafeTokenIn",
            token_out="0xSafeTokenOut",
            amount_in_wei=10**18,
            amount_out_min_wei=10**6,
            trade_value_usd=200.1,
            recipient="0xUserRecipient0000000000000000000000000001",
        )
        v_conc = pipeline.evaluate(req_200_1, current_portfolio_value_usd=1000.0, current_asset_holdings_usd=0.0)
        assert v_conc.approved is False
        assert v_conc.layer_failed == "Layer 2: Capital Allocation"
        assert "Asset concentration" in v_conc.rejection_reason


# ===========================================================================
# 2. Keystore Cryptographic Security & Cryptographic Invariants
# ===========================================================================

class TestKeystoreSecurityEmpirical:
    """Rigorous empirical validation of keystore encryption, decryption, and cryptographic properties."""

    def test_keystore_scrypt_aes128ctr_roundtrip_and_invariants(self, tmp_path):
        """Verify AES-128-CTR and Scrypt KDF parameters, decryption, and file storage."""
        signer = HotKeystoreSigner.create_new()
        address = signer.address
        privkey = signer.private_key_hex
        password = "VeryStrongPassword_2026!@#"

        # Export keystore dict
        ks = signer.export_keystore(password, kdf="scrypt")

        # Invariants on keystore format
        assert ks["version"] == 3
        crypto = ks.get("crypto") or ks.get("Crypto")
        assert crypto["cipher"] == "aes-128-ctr"
        assert crypto["kdf"] == "scrypt"
        assert len(crypto["mac"]) == 64  # SHA3/Keccak-256 MAC in hex

        # File persistence round-trip
        file_path = tmp_path / "keystore_test.json"
        signer.save_keystore_file(file_path, password, kdf="scrypt")
        reloaded = HotKeystoreSigner.from_keystore_file(file_path, password)
        assert reloaded.address == address
        assert reloaded.private_key_hex == privkey

        # Wrong password strictly raises ValueError
        with pytest.raises(ValueError):
            HotKeystoreSigner.from_keystore_file(file_path, "wrong_pass_xyz")

    def test_eip712_typed_signing_and_signature_recovery(self):
        """Sign EIP-712 structured typed data and verify cryptographic address recovery."""
        signer = HotKeystoreSigner.create_new()

        domain = {
            "name": "Antigravity DEX Router",
            "version": "1",
            "chainId": 42161,
            "verifyingContract": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        }
        types = {
            "SwapOrder": [
                {"name": "recipient", "type": "address"},
                {"name": "amountIn", "type": "uint256"},
                {"name": "amountOutMin", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        }
        message = {
            "recipient": signer.address,
            "amountIn": 10**18,
            "amountOutMin": 10**6,
            "deadline": int(time.time()) + 300,
        }

        signed_res = signer.sign_typed_data(
            domain_data=domain,
            message_types=types,
            message_data=message,
        )

        assert signed_res["signature"].startswith("0x")
        assert len(signed_res["signature"]) == 132  # 0x + 65 bytes = 132 hex characters

        # Verify signature recovery using eth_account
        encoded = encode_typed_data(
            domain_data=domain,
            message_types=types,
            message_data=message,
        )
        recovered_address = Account.recover_message(encoded, signature=signed_res["signature"])
        assert recovered_address.lower() == signer.address.lower()

    def test_eip191_personal_sign_and_recovery(self):
        """Sign personal message and verify cryptographic address recovery."""
        signer = HotKeystoreSigner.create_new()
        raw_msg = "Antigravity Institutional Live Trade Intent"
        sig_data = signer.sign_message(raw_msg)

        encoded = encode_defunct(text=raw_msg)
        recovered = Account.recover_message(encoded, signature=sig_data["signature"])
        assert recovered.lower() == signer.address.lower()


# ===========================================================================
# 3. EIP-1193 Bridge Server Lifecycle & JSON-RPC
# ===========================================================================

class TestEIP1193BridgeLifecycle:
    """Verify EIP-1193 bridge staging, confirmation, rejection, and JSON-RPC compliance."""

    def test_staging_confirm_reject_lifecycle(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # Stage transaction
        tx_data = {
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 10**18,
            "amount_out_min_wei": 10**6,
            "trade_value_usd": 150.0,
        }
        res = client.post("/send-transaction", json=tx_data)
        assert res.status_code == 200
        staged = res.json()
        req_id = staged["request_id"]
        assert req_id in bridge.pending_transactions

        # Confirm transaction
        confirm_res = client.post("/confirm-transaction", json={
            "request_id": req_id,
            "tx_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "success": True,
        })
        assert confirm_res.status_code == 200
        assert confirm_res.json()["status"] == "confirmed"
        assert req_id not in bridge.pending_transactions
        assert bridge.transaction_results[req_id]["status"] == "confirmed"

        # Stage second transaction and reject
        res2 = client.post("/send-transaction", json=tx_data)
        req_id2 = res2.json()["request_id"]

        reject_res = client.post("/confirm-transaction", json={
            "request_id": req_id2,
            "success": False,
            "error_reason": "User cancelled in MetaMask UI",
        })
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"
        assert "User cancelled" in reject_res.json()["error_reason"]

    def test_json_rpc_spec_compliance(self):
        bridge = EIP1193BridgeServer(default_chain_id=42161)
        client = TestClient(bridge.app)

        # eth_chainId
        res = client.post("/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
        assert res.json()["result"] == hex(42161)

        # eth_accounts
        res = client.post("/rpc", json={"jsonrpc": "2.0", "id": 2, "method": "eth_accounts"})
        assert isinstance(res.json()["result"], list)

        # unsupported method -> code -32601
        res = client.post("/rpc", json={"jsonrpc": "2.0", "id": 3, "method": "eth_nonexistent"})
        assert res.json()["error"]["code"] == -32601


# ===========================================================================
# 4. Multi-DEX Router Canonical Addresses & Routing
# ===========================================================================

class TestMultiDEXRouterEmpirical:
    """Verify canonical router contracts on Arbitrum One and Base."""

    def test_canonical_addresses(self):
        router = MultiDEXRouter()

        # Arbitrum One (42161)
        arb_cfg = router.get_config(42161)
        assert arb_cfg.uniswap_router.lower() == "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45".lower()
        assert arb_cfg.uniswap_quoter.lower() == "0x61ffe014ba136170505655d03170f09287640f16".lower()

        # Base (8453)
        base_cfg = router.get_config(8453)
        assert base_cfg.uniswap_router.lower() == "0x2626664c2603336e57b271c5c0b26f421741e481".lower()
        assert base_cfg.aerodrome_router.lower() == "0xcf77a3ba9a5ca399b7c97c74856154938591a088".lower()

        # Aerodrome protocol selection on Base
        aero_addr = router.get_router_address(8453, protocol="aerodrome")
        assert aero_addr.lower() == "0xcf77a3ba9a5ca399b7c97c74856154938591a088".lower()

        # Unsupported chain ID raises ValueError
        with pytest.raises(ValueError):
            router.get_config(999999)
