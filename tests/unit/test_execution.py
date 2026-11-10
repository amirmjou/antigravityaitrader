"""
Unit Test Suite for Execution Subsystem (Milestone 2 - Features F08–F14).
Tests HotKeystoreSigner, EIP1193BridgeServer, DualEngineWalletRouter,
PreBroadcastGuardrailPipeline, and MultiDEXRouter.
"""
import json
import pytest
from pathlib import Path
from starlette.testclient import TestClient

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
    create_bridge_app,
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
def web3_arb():
    return MockWeb3Provider(chain_id=42161, base_fee_gwei=0.1)


@pytest.fixture
def web3_base():
    return MockWeb3Provider(chain_id=8453, base_fee_gwei=0.005)


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
def goplus():
    return MockGoPlusClient()


@pytest.fixture
def quoter():
    return MockUniswapV3Quoter(base_price_usd=88500.0, pool_liquidity_usd=50000000.0)


@pytest.fixture
def guardrail(arb_config, web3_arb, goplus, quoter):
    return PreBroadcastGuardrailPipeline(
        chain_config=arb_config,
        web3_provider=web3_arb,
        goplus_client=goplus,
        quoter=quoter,
        max_spend_per_trade_usd=250.0,
        max_asset_concentration_pct=20.0,
        max_daily_drawdown_pct=8.0,
    )


@pytest.fixture
def hot_signer():
    # Known test private key
    test_key = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
    return HotKeystoreSigner.from_private_key(test_key, default_chain_id=42161)


@pytest.fixture
def bridge_server():
    return EIP1193BridgeServer(default_chain_id=42161)


# ===========================================================================
# 1. HotKeystoreSigner Tests
# ===========================================================================

class TestHotKeystoreSigner:
    def test_create_new_account(self):
        signer = HotKeystoreSigner.create_new()
        assert signer.address.startswith("0x")
        assert len(signer.address) == 42
        assert len(signer.private_key_hex) == 66

    def test_from_private_key(self, hot_signer):
        assert hot_signer.address.startswith("0x")
        assert len(hot_signer.address) == 42
        assert hot_signer.private_key_hex == "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"

    def test_keystore_export_and_import(self, hot_signer):
        password = "strong_test_password_123!"
        keystore_dict = hot_signer.export_keystore(password, kdf="scrypt")
        assert "crypto" in keystore_dict or "Crypto" in keystore_dict

        # Decrypt back
        imported_signer = HotKeystoreSigner.from_keystore_json(keystore_dict, password)
        assert imported_signer.address == hot_signer.address

    def test_keystore_file_persistence(self, hot_signer, tmp_path):
        key_file = tmp_path / "test_keystore.json"
        password = "another_password_456"
        saved_path = hot_signer.save_keystore_file(key_file, password)
        assert saved_path.exists()

        restored_signer = HotKeystoreSigner.from_keystore_file(saved_path, password)
        assert restored_signer.address == hot_signer.address

    def test_nonce_tracking_and_increment(self, hot_signer):
        hot_signer.set_nonce(5)
        assert hot_signer.get_nonce() == 5

        tx_dict = {
            "to": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            "value": 1000,
            "gas": 21000,
            "maxFeePerGas": 2000000000,
            "maxPriorityFeePerGas": 1000000000,
            "chainId": 42161,
        }
        res = hot_signer.sign_transaction(tx_dict)
        assert res["nonce"] == 5
        assert hot_signer.get_nonce() == 6

    def test_estimate_eip1559_fees(self, hot_signer, web3_arb):
        hot_signer.w3 = web3_arb
        fees = hot_signer.estimate_eip1559_fees(base_fee_gwei=0.1, priority_fee_gwei=0.05)
        assert fees["baseFeePerGas"] == 100_000_000
        assert fees["maxPriorityFeePerGas"] == 50_000_000
        # maxFeePerGas = 2 * 100M + 50M = 250M wei
        assert fees["maxFeePerGas"] == 250_000_000

    def test_sign_transaction_output(self, hot_signer):
        tx_dict = {
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "value": 0,
            "gas": 150000,
            "chainId": 42161,
        }
        res = hot_signer.sign_transaction(tx_dict)
        assert res["raw_transaction"].startswith("0x")
        assert res["tx_hash"].startswith("0x")
        assert len(res["tx_hash"]) == 66
        assert res["r"] > 0
        assert res["s"] > 0

    def test_sign_personal_message(self, hot_signer):
        msg = "Authorize trade allocation $100"
        signed = hot_signer.sign_message(msg)
        assert signed["signature"].startswith("0x") or len(signed["signature"]) == 130
        assert signed["message_hash"].startswith("0x")

    def test_sign_typed_data(self, hot_signer):
        domain = {
            "name": "Antigravity Trading",
            "version": "1",
            "chainId": 42161,
            "verifyingContract": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        }
        types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TradeOrder": [
                {"name": "recipient", "type": "address"},
                {"name": "amountIn", "type": "uint256"},
            ],
        }
        data = {
            "recipient": hot_signer.address,
            "amountIn": 1000000,
        }
        signed = hot_signer.sign_typed_data(domain, types, data)
        assert "signature" in signed
        assert "message_hash" in signed


# ===========================================================================
# 2. EIP1193BridgeServer Tests
# ===========================================================================

class TestEIP1193BridgeServer:
    def test_bridge_status_endpoint(self, bridge_server):
        client = TestClient(bridge_server.app)
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["chain_id"] == 42161
        assert "0xUserWallet" in data["connected_accounts"]

    def test_request_accounts(self, bridge_server):
        client = TestClient(bridge_server.app)
        response = client.get("/request-accounts")
        assert response.status_code == 200
        assert response.json()["accounts"] == ["0xUserWallet"]

    def test_send_and_confirm_transaction(self, bridge_server):
        client = TestClient(bridge_server.app)
        send_req = {
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 10**17,
            "amount_out_min_wei": 950000,
            "trade_value_usd": 100.0,
        }
        res = client.post("/send-transaction", json=send_req)
        assert res.status_code == 200
        staged = res.json()
        req_id = staged["request_id"]
        assert req_id in bridge_server.pending_transactions

        # Confirm from MetaMask UI
        tx_hash = "0x" + "aa" * 32
        confirm_res = client.post("/confirm-transaction", json={
            "request_id": req_id,
            "tx_hash": tx_hash,
            "success": True,
        })
        assert confirm_res.status_code == 200
        assert confirm_res.json()["status"] == "confirmed"
        assert req_id not in bridge_server.pending_transactions

    def test_send_and_reject_transaction(self, bridge_server):
        client = TestClient(bridge_server.app)
        send_req = {
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 10**17,
            "amount_out_min_wei": 950000,
        }
        res = client.post("/send-transaction", json=send_req)
        req_id = res.json()["request_id"]

        reject_res = client.post("/confirm-transaction", json={
            "request_id": req_id,
            "success": False,
            "error_reason": "User clicked Reject in MetaMask",
        })
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"
        assert "Reject" in reject_res.json()["error_reason"]

    def test_json_rpc_methods(self, bridge_server):
        client = TestClient(bridge_server.app)

        # eth_accounts
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_accounts", "id": 1})
        assert res.status_code == 200
        assert res.json()["result"] == ["0xUserWallet"]

        # eth_chainId
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 2})
        assert res.status_code == 200
        assert res.json()["result"] == hex(42161)

        # net_version
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "net_version", "id": 3})
        assert res.status_code == 200
        assert res.json()["result"] == "42161"

        # eth_sendTransaction
        tx_call = {
            "jsonrpc": "2.0",
            "method": "eth_sendTransaction",
            "params": [{"to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45", "value": "0x0"}],
            "id": 4,
        }
        res = client.post("/rpc", json=tx_call)
        assert res.status_code == 200
        assert res.json()["result"].startswith("0x")

        # Unsupported method
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_unsupportedOp", "id": 5})
        assert res.status_code == 200
        assert "error" in res.json()


# ===========================================================================
# 3. DualEngineWalletRouter Tests
# ===========================================================================

class TestDualEngineWalletRouter:
    def test_hot_keystore_execution(self, web3_arb, arb_config, hot_signer):
        router = DualEngineWalletRouter(web3_provider=web3_arb, chain_config=arb_config, hot_signer=hot_signer)
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = router.execute_swap(req, signer_mode="hot_keystore")
        assert res.success is True
        assert res.signer_mode == "hot_keystore"
        assert res.tx_hash.startswith("0x")
        assert len(res.tx_hash) == 66
        assert res.gas_used == 145000

    def test_eip1193_metamask_execution(self, web3_arb, arb_config, bridge_server):
        router = DualEngineWalletRouter(web3_provider=web3_arb, chain_config=arb_config, bridge_server=bridge_server)
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xUserWallet",
            trade_value_usd=100.0,
        )
        res = router.execute_swap(req, signer_mode="eip1193_metamask")
        assert res.success is True
        assert res.signer_mode == "eip1193_metamask"
        assert res.tx_hash.startswith("0x")

    def test_revert_handling(self, web3_arb, arb_config):
        router = DualEngineWalletRouter(web3_provider=web3_arb, chain_config=arb_config)
        web3_arb.set_revert_trigger("UniswapV3: SLIPPAGE_EXCEEDED")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
        )
        res = router.execute_swap(req)
        assert res.success is False
        assert "UniswapV3: SLIPPAGE_EXCEEDED" in res.revert_reason
        web3_arb.set_revert_trigger(None)


# ===========================================================================
# 4. PreBroadcastGuardrailPipeline Tests
# ===========================================================================

class TestPreBroadcastGuardrailPipeline:
    def test_layer1_honeypot_rejection(self, guardrail):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xBadHoneypotTokenAddress0000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 1: Contract Security"
        assert "Honeypot detected" in verdict.rejection_reason

    def test_layer1_high_tax_rejection(self, guardrail):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xHighTaxTokenAddress0000000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert "Tax exceeds 1% ceiling" in verdict.rejection_reason

    def test_layer2_per_trade_cap(self, guardrail):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=300.0,  # Exceeds $250 cap
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 2: Capital Allocation"
        assert "exceeds cap of $250.0" in verdict.rejection_reason

    def test_layer2_asset_concentration(self, guardrail):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=200.0,
        )
        # 1000 + 200 = 1200 / 5000 = 24% > 20%
        verdict = guardrail.evaluate(req, current_portfolio_value_usd=5000.0, current_asset_holdings_usd=1000.0)
        assert verdict.approved is False
        assert "Asset concentration" in verdict.rejection_reason

    def test_layer2_drawdown_circuit_breaker(self, guardrail):
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req, current_daily_drawdown_pct=8.5)
        assert verdict.approved is False
        assert "Daily drawdown 8.5% exceeds circuit breaker 8.0%" in verdict.rejection_reason

    def test_layer3_slippage_and_price_impact(self, guardrail):
        # Slippage > 100 bps
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            slippage_bps=150,
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 3: Dynamic Slippage"

        # Price impact > 2.0%
        req.slippage_bps = 50
        verdict = guardrail.evaluate(req, override_quoter_impact_pct=3.1)
        assert verdict.approved is False
        assert "Price impact 3.10% exceeds 2.0% threshold" in verdict.rejection_reason

    def test_layer4_gas_and_congestion(self, guardrail, web3_arb):
        # Base fee spike
        web3_arb.base_fee_gwei = 130.0
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 4: Gas & Congestion"
        web3_arb.base_fee_gwei = 0.1

    def test_layer5_simulation_revert(self, guardrail, web3_arb):
        web3_arb.set_revert_trigger("UniswapV3: K")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert verdict.layer_failed == "Layer 5: Pre-Flight Simulation"
        assert "UniswapV3: K" in verdict.rejection_reason
        web3_arb.set_revert_trigger(None)


# ===========================================================================
# 5. MultiDEXRouter Tests
# ===========================================================================

class TestMultiDEXRouter:
    def test_router_address_resolutions(self):
        router = MultiDEXRouter()
        # Arbitrum
        assert router.get_router_address(42161) == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
        assert router.get_quoter_address(42161) == "0x61fFE014bA136170505655d03170F09287640F16"

        # Base Uniswap
        assert router.get_router_address(8453) == "0x2626664c2603336E57B271c5C0b26F421741e481"
        assert router.get_quoter_address(8453) == "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"

        # Base Aerodrome
        assert router.get_router_address(8453, protocol="aerodrome") == "0xcF77a3Ba9A5CA399B7c97c74856154938591A088"

    def test_build_swap_transaction(self):
        router = MultiDEXRouter()
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            deadline_seconds=300,
        )
        tx = router.build_swap_transaction(req, signer_address="0xHotSigner")
        assert tx["to"] == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
        assert tx["from"] == "0xHotSigner"
        assert "swap_params" in tx
        assert tx["swap_params"]["tokenIn"] == req.token_in
        assert tx["swap_params"]["amountIn"] == req.amount_in_wei

    def test_build_approval_transaction(self):
        router = MultiDEXRouter()
        tx = router.build_approval_transaction(
            token_address="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            spender_address="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            amount_wei=10**18,
            signer_address="0xHotSigner",
            chain_id=42161,
        )
        assert tx["to"] == "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
        assert tx["spender"] == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
        assert tx["amount"] == 10**18

    def test_unsupported_chain_raises_value_error(self):
        router = MultiDEXRouter()
        with pytest.raises(ValueError, match="Unsupported chain_id: 999999"):
            router.get_config(999999)

    def test_route_and_execute_delegation(self, web3_arb, arb_config, hot_signer):
        dex_router = MultiDEXRouter()
        wallet_router = DualEngineWalletRouter(web3_provider=web3_arb, chain_config=arb_config, hot_signer=hot_signer)
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = dex_router.route_and_execute(req, wallet_router, signer_mode="hot_keystore")
        assert res.success is True
        assert res.gas_used == 145000


# ===========================================================================
# 6. Additional Edge Cases & Error Handling Tests
# ===========================================================================

class TestExecutionEdgeCases:
    def test_keystore_wrong_password_raises(self, hot_signer):
        keystore_dict = hot_signer.export_keystore("correct_password")
        with pytest.raises(ValueError):
            HotKeystoreSigner.from_keystore_json(keystore_dict, "wrong_password")

    def test_unsupported_signer_mode_in_router(self, web3_arb, arb_config):
        router = DualEngineWalletRouter(web3_provider=web3_arb, chain_config=arb_config)
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
        )
        res = router.execute_swap(req, signer_mode="invalid_engine")
        assert res.success is False
        assert "Unsupported signer_mode" in res.revert_reason

    def test_layer1_transfer_restriction_detection(self, guardrail):
        # Create a mock token that cannot be sold
        guardrail.goplus.token_database["0xCannotSellToken"] = {
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
        verdict = guardrail.evaluate(req)
        assert verdict.approved is False
        assert "Transfer restriction or blacklist" in verdict.rejection_reason

    def test_hot_signer_resync_nonce(self, hot_signer, web3_arb):
        hot_signer.w3 = web3_arb
        hot_signer.set_nonce(42)
        assert hot_signer.get_nonce() == 42
        # Without web3.eth.get_transaction_count, resync resets to 0
        hot_signer.resync_nonce()
        assert hot_signer.get_nonce() == 0

    def test_eip1193_bridge_set_account_and_factory(self):
        app = create_bridge_app(default_chain_id=8453)
        client = TestClient(app)
        res = client.get("/status")
        assert res.status_code == 200
        assert res.json()["chain_id"] == 8453

