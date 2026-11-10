"""
Adversarial Verification & Boundary Attack Suite (Milestone 6 Iteration 2).
Author: teamwork_challenger_m6_it2_1 (Critic / Specialist)

Comprehensive empirical test suite covering:
1. Re-testing of the 5 vulnerabilities previously identified by Challenger 1:
   - Non-dict / array payloads to /wallet_syncAccount
   - Non-scalar chain_id to /wallet_syncAccount and /rpc
   - Non-hex addresses to /wallet_syncAccount
   - Negative and zero chain IDs to /wallet_syncAccount
2. New Boundary Attacks:
   - Empty body {}, None body, empty string ""
   - Mixed-case valid hex addresses vs invalid lengths (41/43 chars, no 0x prefix, non-hex chars)
   - Chain IDs with leading/trailing whitespace, hex strings ("0xa4b1", "0XA4B1"), decimal strings ("42161")
   - Boolean chain IDs (True/False rejected instead of treated as 1/0)
   - Float chain IDs (42161.5, "42161.5")
   - EIP-155 violations (0, "0", -1, "-1", "-0x1")
3. RPC endpoint (/rpc) robustness:
   - Address injection resistance (invalid addresses ignored, no state pollution)
   - Chain ID validation in JSON-RPC format (-32602 error code returned)
4. Malformed raw payloads:
   - Corrupt JSON syntax
   - Zero-byte empty payload
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_live_metamask_terminal import LIVE_SESSION_TOKEN, build_live_app
from visualization.server.security import global_rate_limiter, global_simulation_cache

VALID_ETH_ADDR = "0x1234567890123456789012345678901234567890"
MIXED_CASE_ADDR = "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12"


@pytest.fixture(autouse=True)
def reset_security_state():
    """Reset rate limiter and simulation cache between tests."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()


@pytest.fixture
def client():
    """Create test client in production security mode."""
    os.environ["TRADINGAGENTS_SECURITY_MODE"] = "production"
    os.environ["TRADING_API_KEY"] = LIVE_SESSION_TOKEN
    app = build_live_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}


# ==============================================================================
# SECTION 1: Challenger 1 Vulnerabilities Re-Test
# ==============================================================================

class TestChallenger1VulnerabilitiesRemediation:
    """Empirically validates the 5 vulnerabilities previously reported by Challenger 1."""

    def test_repro_vulnerability_1_non_dict_payload_array(self, client, auth_headers):
        """JSON array payload with valid parameters: must succeed (200) without 500 crash."""
        res = client.post("/wallet_syncAccount", json=[VALID_ETH_ADDR, 42161], headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synchronized"
        assert data["chain_id"] == 42161
        assert data["connected_accounts"][0] == VALID_ETH_ADDR

    def test_repro_vulnerability_1_non_dict_payload_primitives(self, client, auth_headers):
        """JSON primitive payloads: must return HTTP 400 Bad Request, never 500 crash."""
        for prim in ["just_a_string", 12345, True, False, []]:
            res = client.post("/wallet_syncAccount", json=prim, headers=auth_headers)
            assert res.status_code == 400, f"Expected 400 for primitive {prim}, got {res.status_code}"
            assert res.status_code != 500

    def test_repro_vulnerability_2_non_scalar_chain_id_wallet_sync(self, client, auth_headers):
        """Non-scalar chain_id (list or dict) to /wallet_syncAccount: must return 400, never 500."""
        for bad_cid in [[1, 2], {"id": 1}, [42161]]:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": VALID_ETH_ADDR, "chain_id": bad_cid},
                headers=auth_headers,
            )
            assert res.status_code == 400, f"Expected 400 for bad chain_id {bad_cid}, got {res.status_code}"
            assert res.status_code != 500

    def test_repro_vulnerability_3_non_scalar_chain_id_rpc(self, client, auth_headers):
        """Non-scalar chain_id in /rpc wallet_syncAccount: must return JSON-RPC error -32602, never 500."""
        for bad_cid in [[1, 2], {"id": 1}]:
            res = client.post(
                "/rpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "wallet_syncAccount",
                    "params": [VALID_ETH_ADDR, bad_cid],
                    "id": 99,
                },
                headers=auth_headers,
            )
            assert res.status_code == 200  # JSON-RPC returns 200 with error object
            data = res.json()
            assert "error" in data, f"Expected JSON-RPC error for {bad_cid}, got {data}"
            assert data["error"]["code"] == -32602

    def test_repro_vulnerability_4_non_hex_address_wallet_sync(self, client, auth_headers):
        """Non-hex strings and XSS tags to /wallet_syncAccount: must be rejected with HTTP 400."""
        hostile_addrs = [
            "not_an_eth_address",
            "<script>alert(1)</script>",
            "0x123",  # truncated
            "0x" + "Z" * 40,  # non-hex
            "' OR '1'='1",
            "0xUserWallet",  # Cannot be injected via REST endpoint
        ]
        for bad_addr in hostile_addrs:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": bad_addr, "chain_id": 42161},
                headers=auth_headers,
            )
            assert res.status_code in [400, 422], f"Expected 400/422 for address {bad_addr}, got {res.status_code}"
            assert res.status_code != 500

    def test_repro_vulnerability_5_negative_and_zero_chain_id_wallet_sync(self, client, auth_headers):
        """Negative and zero chain IDs: must be rejected with HTTP 400 (violates EIP-155)."""
        invalid_cids = [-1, 0, -42161, "-1", "0", "-0x1", "-0x2a"]
        for bad_cid in invalid_cids:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": VALID_ETH_ADDR, "chain_id": bad_cid},
                headers=auth_headers,
            )
            assert res.status_code == 400, f"Expected 400 for chain_id {bad_cid}, got {res.status_code}"
            assert res.status_code != 500


# ==============================================================================
# SECTION 2: Iteration 2 New Boundary Attacks
# ==============================================================================

class TestIteration2BoundaryAttacks:
    """Stress tests new edge cases and boundary boundaries for live endpoints."""

    def test_empty_json_object_body(self, client, auth_headers):
        """Empty JSON object {} must be rejected with 400 (missing address), not crash."""
        res = client.post("/wallet_syncAccount", json={}, headers=auth_headers)
        assert res.status_code == 400
        assert "Invalid Ethereum address format" in res.json().get("detail", "")

    def test_none_body_in_json(self, client, auth_headers):
        """JSON null body must be rejected with 400, not crash."""
        res = client.post("/wallet_syncAccount", json=None, headers=auth_headers)
        assert res.status_code == 400
        assert res.status_code != 500

    def test_empty_string_json_body(self, client, auth_headers):
        """Empty string \"\" JSON body must be rejected with 400, not crash."""
        res = client.post("/wallet_syncAccount", json="", headers=auth_headers)
        assert res.status_code == 400
        assert res.status_code != 500

    def test_mixed_case_valid_hex_address(self, client, auth_headers):
        """Mixed-case (EIP-55 checksummed) address must be accepted and synchronized."""
        res = client.post(
            "/wallet_syncAccount",
            json={"account": MIXED_CASE_ADDR, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["connected_accounts"][0] == MIXED_CASE_ADDR

    def test_invalid_address_lengths(self, client, auth_headers):
        """Addresses with 41 chars or 43 chars (off-by-one length) must be rejected with 400."""
        # 41 chars (0x + 39 hex chars)
        short_addr = "0x" + "a" * 39
        res_short = client.post(
            "/wallet_syncAccount",
            json={"account": short_addr, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res_short.status_code == 400

        # 43 chars (0x + 41 hex chars)
        long_addr = "0x" + "a" * 41
        res_long = client.post(
            "/wallet_syncAccount",
            json={"account": long_addr, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res_long.status_code == 400

    def test_address_missing_0x_prefix(self, client, auth_headers):
        """Valid 40-char hex string without '0x' prefix must be rejected with 400."""
        no_prefix = "1234567890123456789012345678901234567890"
        res = client.post(
            "/wallet_syncAccount",
            json={"account": no_prefix, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_address_with_internal_whitespace(self, client, auth_headers):
        """Address with internal whitespace '0x 123...' must be rejected with 400."""
        ws_addr = "0x 123456789012345678901234567890123456789"
        res = client.post(
            "/wallet_syncAccount",
            json={"account": ws_addr, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_chain_id_with_whitespace(self, client, auth_headers):
        """Chain ID with leading and trailing whitespace must be properly trimmed and accepted."""
        # Decimal with spaces
        res_dec = client.post(
            "/wallet_syncAccount",
            json={"account": VALID_ETH_ADDR, "chain_id": "  42161  "},
            headers=auth_headers,
        )
        assert res_dec.status_code == 200
        assert res_dec.json()["chain_id"] == 42161

        # Hex with spaces
        res_hex = client.post(
            "/wallet_syncAccount",
            json={"account": VALID_ETH_ADDR, "chain_id": "  0xa4b1  "},
            headers=auth_headers,
        )
        assert res_hex.status_code == 200
        assert res_hex.json()["chain_id"] == 42161

    def test_chain_id_uppercase_hex_prefix(self, client, auth_headers):
        """Chain ID with uppercase '0X' prefix must be accepted."""
        res = client.post(
            "/wallet_syncAccount",
            json={"account": VALID_ETH_ADDR, "chain_id": "0XA4B1"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["chain_id"] == 42161

    def test_chain_id_boolean_types_strictly_rejected(self, client, auth_headers):
        """
        Boolean chain IDs (True/False) must be rejected with 400.
        In Python bool is a subclass of int, so without explicit rejection,
        True would improperly evaluate to chain ID 1 (Ethereum Mainnet).
        """
        for b_val in [True, False]:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": VALID_ETH_ADDR, "chain_id": b_val},
                headers=auth_headers,
            )
            assert res.status_code == 400, f"Expected 400 for boolean chain_id {b_val}, got {res.status_code}"

    def test_chain_id_floats_strictly_rejected(self, client, auth_headers):
        """Float chain IDs (numeric 42161.5 or string '42161.5') must be rejected with 400."""
        for f_val in [42161.5, "42161.5", 1.0, "1.0"]:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": VALID_ETH_ADDR, "chain_id": f_val},
                headers=auth_headers,
            )
            assert res.status_code == 400, f"Expected 400 for float chain_id {f_val}, got {res.status_code}"

    def test_large_valid_chain_ids(self, client, auth_headers):
        """Verify well-known large EVM chain IDs are correctly handled."""
        networks = [
            (1, "Ethereum Mainnet"),
            (10, "Optimism"),
            (137, "Polygon"),
            (8453, "Base"),
            (42161, "Arbitrum One"),
            (11155111, "Sepolia Testnet"),
            (2147483647, "Max 32-bit int"),
        ]
        for cid, net_name in networks:
            res = client.post(
                "/wallet_syncAccount",
                json={"account": VALID_ETH_ADDR, "chain_id": cid},
                headers=auth_headers,
            )
            assert res.status_code == 200, f"Failed for {net_name} ({cid}): {res.text}"
            assert res.json()["chain_id"] == cid


# ==============================================================================
# SECTION 3: JSON-RPC Boundary & State Pollution Hardening
# ==============================================================================

class TestRpcBoundaryHardening:
    """Stress tests POST /rpc under adversarial parameters."""

    def test_rpc_wallet_sync_rejects_negative_chain_id(self, client, auth_headers):
        """Negative chain ID in /rpc params[1] returns JSON-RPC -32602 error."""
        res = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "wallet_syncAccount",
                "params": [VALID_ETH_ADDR, -42161],
                "id": 101,
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == -32602

    def test_rpc_wallet_sync_rejects_zero_chain_id(self, client, auth_headers):
        """Zero chain ID in /rpc params[1] returns JSON-RPC -32602 error."""
        res = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "wallet_syncAccount",
                "params": [VALID_ETH_ADDR, 0],
                "id": 102,
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == -32602

    def test_rpc_wallet_sync_ignores_invalid_address_without_state_pollution(self, client, auth_headers):
        """Invalid address in /rpc params[0] must NOT be added to connected_accounts."""
        malicious = "<script>alert('pwned')</script>"
        res = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "wallet_syncAccount",
                "params": [malicious, 42161],
                "id": 103,
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        accounts = data.get("result", [])
        assert malicious not in accounts

    def test_rpc_eth_chain_id_round_trip(self, client, auth_headers):
        """Setting chain ID via /wallet_syncAccount reflects accurately in eth_chainId & net_version."""
        # 1. Set to Arbitrum One (42161 = 0xa4b1)
        res_sync = client.post(
            "/wallet_syncAccount",
            json={"account": VALID_ETH_ADDR, "chain_id": 42161},
            headers=auth_headers,
        )
        assert res_sync.status_code == 200

        # 2. Query eth_chainId
        res_cid = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 104},
            headers=auth_headers,
        )
        assert res_cid.status_code == 200
        assert res_cid.json()["result"] == "0xa4b1"

        # 3. Query net_version
        res_net = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "net_version", "params": [], "id": 105},
            headers=auth_headers,
        )
        assert res_net.status_code == 200
        assert res_net.json()["result"] == "42161"


# ==============================================================================
# SECTION 4: Raw Malformed Payload Transport Edge Cases
# ==============================================================================

class TestRawPayloadEdgeCases:
    """Tests transport-level corrupt bytes and non-standard payloads."""

    def test_corrupt_json_bytes_to_wallet_sync(self, client, auth_headers):
        """Malformed JSON syntax must return HTTP 400 Bad Request, never 500."""
        headers = dict(auth_headers)
        headers["Content-Type"] = "application/json"
        res = client.post("/wallet_syncAccount", content=b"{corrupt_json: true,", headers=headers)
        assert res.status_code == 400
        assert res.status_code != 500

    def test_empty_raw_bytes_to_wallet_sync(self, client, auth_headers):
        """Zero-byte payload must return HTTP 400 Bad Request, never 500."""
        headers = dict(auth_headers)
        headers["Content-Type"] = "application/json"
        res = client.post("/wallet_syncAccount", content=b"", headers=headers)
        assert res.status_code == 400
        assert res.status_code != 500


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))
