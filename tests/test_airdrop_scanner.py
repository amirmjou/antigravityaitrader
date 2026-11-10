"""Unit tests for the MetaMask EVM Airdrop & Activity Scanner."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crypto_pipeline.airdrop_scanner import (
    EVMAirdropScanner,
    format_markdown_report,
    validate_evm_address,
)


def test_validate_evm_address_valid() -> None:
    addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    assert validate_evm_address(f"  {addr} ") == addr


def test_validate_evm_address_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid EVM address"):
        validate_evm_address("not-an-address")


def test_scan_wallet_and_readiness_score() -> None:
    mock_session = MagicMock()

    def side_effect_post(url: str, json: dict, timeout: float):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        method = json["method"]
        if method == "eth_getBalance":
            # 0.05 ETH in hex wei
            resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": hex(int(0.05 * 1e18))}
        elif method == "eth_getTransactionCount":
            # 12 txs per chain
            resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": hex(12)}
        return resp

    mock_session.post.side_effect = side_effect_post

    networks = {
        "ethereum": {"name": "Ethereum Mainnet", "rpc_urls": ["https://eth.example"], "symbol": "ETH", "is_testnet": False},
        "arbitrum": {"name": "Arbitrum One", "rpc_urls": ["https://arb.example"], "symbol": "ETH", "is_testnet": False},
        "base": {"name": "Base", "rpc_urls": ["https://base.example"], "symbol": "ETH", "is_testnet": False},
        "sepolia": {"name": "Sepolia Testnet", "rpc_urls": ["https://sep.example"], "symbol": "SEP-ETH", "is_testnet": True},
    }

    scanner = EVMAirdropScanner(networks=networks, session=mock_session)
    report = scanner.scan_wallet("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")

    assert report.active_mainnet_chains == 3
    assert report.total_mainnet_txs == 36
    assert report.total_mainnet_eth == pytest.approx(0.15)
    assert report.readiness_score >= 70
    assert "Drops.bot (Unclaimed Airdrops)" in report.checker_links


def test_fetch_tokenless_protocols_filters_correctly() -> None:
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {
            "name": "Polymarket",
            "symbol": "-",
            "gecko_id": None,
            "category": "Prediction Market",
            "tvl": 120_000_000,
            "change_7d": 14.2,
            "chains": ["Polygon"],
            "url": "https://polymarket.com",
            "slug": "polymarket",
        },
        {
            "name": "Uniswap",
            "symbol": "UNI",
            "gecko_id": "uniswap",
            "category": "Dexs",
            "tvl": 5_000_000_000,
            "chains": ["Ethereum", "Arbitrum"],
            "url": "https://uniswap.org",
            "slug": "uniswap",
        },
        {
            "name": "SolanaOnlyProto",
            "symbol": None,
            "gecko_id": None,
            "category": "Lending",
            "tvl": 90_000_000,
            "chains": ["Solana"],
            "url": "https://sol.example",
            "slug": "sol-only",
        },
    ]
    mock_session.get.return_value = mock_resp

    scanner = EVMAirdropScanner(session=mock_session)
    protocols = scanner.fetch_tokenless_protocols(min_tvl_usd=10_000_000, limit=10)

    assert len(protocols) == 1
    assert protocols[0].name == "Polymarket"
    assert protocols[0].evm_chains == ["Polygon"]

    md = format_markdown_report(None, protocols)
    assert "Polymarket" in md
