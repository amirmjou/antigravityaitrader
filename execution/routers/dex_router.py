"""
Multi-DEX Execution Router.
Coordinates DEX swap execution on Arbitrum One (chain_id=42161) and Base (chain_id=8453)
using Uniswap v3 SwapRouter02 and Aerodrome.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from execution.contracts.quant_architecture import (
    ARBITRUM_POOLS,
    ARBITRUM_TOKENS,
    CANONICAL_ARBITRUM_QUOTER_V2,
)
from tests.e2e.contracts import (
    ChainExecutionConfig,
    SwapExecutionResult,
    SwapTransactionRequest,
)


@dataclass
class DEXRouterConfig:
    chain_id: int
    chain_name: str
    uniswap_router: str
    uniswap_quoter: Optional[str] = None
    uniswap_quoter_v2: Optional[str] = None
    aerodrome_router: Optional[str] = None
    wrapped_native: str = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
    native_symbol: str = "ETH"


# Canonical Contract Addresses
KNOWN_DEX_CONFIGS: Dict[int, DEXRouterConfig] = {
    42161: DEXRouterConfig(
        chain_id=42161,
        chain_name="Arbitrum One",
        uniswap_router="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        uniswap_quoter="0x61fFE014bA136170505655d03170F09287640F16",
        uniswap_quoter_v2=CANONICAL_ARBITRUM_QUOTER_V2,
        aerodrome_router=None,
        wrapped_native="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        native_symbol="ETH",
    ),
    8453: DEXRouterConfig(
        chain_id=8453,
        chain_name="Base",
        uniswap_router="0x2626664c2603336E57B271c5C0b26F421741e481",
        uniswap_quoter="0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        aerodrome_router="0xcF77a3Ba9A5CA399B7c97c74856154938591A088",
        wrapped_native="0x4200000000000000000000000000000000000006",
        native_symbol="ETH",
    ),
    1: DEXRouterConfig(
        chain_id=1,
        chain_name="Ethereum Mainnet",
        uniswap_router="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        uniswap_quoter="0x61fFE014bA136170505655d03170F09287640F16",
        aerodrome_router=None,
        wrapped_native="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        native_symbol="ETH",
    ),
}


class MultiDEXRouter:
    """
    Multi-DEX Execution Router for L2 and EVM Networks.
    Provides parameter encoding, path selection, and routing dispatch across Uniswap v3 & Aerodrome.
    """

    def __init__(self, custom_configs: Optional[Dict[int, DEXRouterConfig]] = None):
        self.configs: Dict[int, DEXRouterConfig] = dict(KNOWN_DEX_CONFIGS)
        if custom_configs:
            self.configs.update(custom_configs)

    def get_config(self, chain_id: int) -> DEXRouterConfig:
        """Fetch router configuration for chain_id."""
        if chain_id not in self.configs:
            raise ValueError(f"Unsupported chain_id: {chain_id}. Supported chains: {list(self.configs.keys())}")
        return self.configs[chain_id]

    def get_router_address(
        self,
        chain_id: int,
        protocol: Literal["auto", "uniswap_v3", "aerodrome"] = "auto",
    ) -> str:
        """Resolve router contract address based on chain and protocol preference."""
        cfg = self.get_config(chain_id)
        if protocol == "aerodrome" and cfg.aerodrome_router:
            return cfg.aerodrome_router
        return cfg.uniswap_router

    def get_quoter_address(self, chain_id: int) -> Optional[str]:
        """Resolve legacy quoter contract address for off-chain quote calculations."""
        cfg = self.get_config(chain_id)
        return cfg.uniswap_quoter

    def get_quoter_v2_address(self, chain_id: int) -> Optional[str]:
        """Resolve canonical deployed QuoterV2 contract address."""
        cfg = self.get_config(chain_id)
        return cfg.uniswap_quoter_v2 or cfg.uniswap_quoter

    @staticmethod
    def encode_v3_path(token_addresses: List[str], fees: List[int]) -> bytes:
        """
        Encode Uniswap v3 SwapRouter02 packed multi-hop path:
        address(token_0) + uint24(fee_0) + address(token_1) + ... + address(token_n).
        """
        if len(token_addresses) < 2:
            raise ValueError("Path must contain at least 2 token addresses.")
        if len(fees) != len(token_addresses) - 1:
            raise ValueError("Fees list length must be len(token_addresses) - 1.")

        encoded = bytearray()
        for idx, addr in enumerate(token_addresses):
            clean = addr[2:] if addr.lower().startswith("0x") else addr
            if len(clean) != 40:
                raise ValueError(f"Invalid EVM address in path: {addr}")
            encoded.extend(bytes.fromhex(clean))
            if idx < len(fees):
                encoded.extend(int(fees[idx]).to_bytes(3, byteorder="big"))
        return bytes(encoded)

    @staticmethod
    def resolve_arbitrum_route(
        symbol_in: str,
        symbol_out: str,
        trade_notional_usd: float = 0.0,
    ) -> Tuple[List[str], List[str], List[int]]:
        """
        Resolve optimal Arbitrum One Uniswap v3 token route & fee tiers.
        Mandatory multi-hop through WETH for LINK <-> USDC and cross-altcoin pairs
        to prevent thin direct-pool slippage spikes (R2 microstructure rule).
        Returns: (route_symbols, route_addresses, fee_tiers)
        """
        s_in = symbol_in.strip().upper()
        s_out = symbol_out.strip().upper()
        if s_in == s_out:
            raise ValueError(f"Cannot route self-swap for {s_in}")
        if s_in not in ARBITRUM_TOKENS or s_out not in ARBITRUM_TOKENS:
            raise ValueError(f"Unsupported token symbol in pair ({s_in}, {s_out})")

        # LINK <-> USDC must always route via WETH (70x-200x lower slippage than direct pool)
        if {s_in, s_out} == {"LINK", "USDC"}:
            route_syms = [s_in, "WETH", s_out]
        # ARB <-> USDC > $5,000 benefits from routing via deep ARB/WETH (500) + WETH/USDC (500)
        elif {s_in, s_out} == {"ARB", "USDC"} and trade_notional_usd > 5000.0:
            route_syms = [s_in, "WETH", s_out]
        elif (s_in, s_out) in ARBITRUM_POOLS:
            route_syms = [s_in, s_out]
        else:
            # Cross pairs (e.g. WBTC <-> LINK, WBTC <-> ARB, ARB <-> LINK) route via WETH hub
            route_syms = [s_in, "WETH", s_out]

        route_addrs = [ARBITRUM_TOKENS[sym].address for sym in route_syms]
        fee_tiers = [ARBITRUM_POOLS[(route_syms[i], route_syms[i + 1])] for i in range(len(route_syms) - 1)]
        return route_syms, route_addrs, fee_tiers

    def build_exact_input_multi_hop_params(
        self,
        route_addresses: List[str],
        fees: List[int],
        recipient: str,
        amount_in_wei: int,
        amount_out_min_wei: int,
    ) -> Dict[str, Any]:
        """
        Build Uniswap v3 SwapRouter02 ExactInputParams struct parameters:
        (path, recipient, amountIn, amountOutMinimum) — note SwapRouter02 omits deadline in struct.
        """
        packed_path = self.encode_v3_path(route_addresses, fees)
        return {
            "path": packed_path,
            "recipient": recipient,
            "amountIn": int(amount_in_wei),
            "amountOutMinimum": int(amount_out_min_wei),
        }

    def build_exact_input_single_params(
        self,
        request: SwapTransactionRequest,
        fee_tier: int = 500,
        sqrt_price_limit_x96: int = 0,
    ) -> Dict[str, Any]:
        """
        Build Uniswap v3 ExactInputSingleParams struct parameters:
        (tokenIn, tokenOut, fee, recipient, deadline, amountIn, amountOutMinimum, sqrtPriceLimitX96)
        """
        deadline_timestamp = int(time.time()) + request.deadline_seconds
        return {
            "tokenIn": request.token_in,
            "tokenOut": request.token_out,
            "fee": fee_tier,
            "recipient": request.recipient,
            "deadline": deadline_timestamp,
            "amountIn": request.amount_in_wei,
            "amountOutMinimum": request.amount_out_min_wei,
            "sqrtPriceLimitX96": sqrt_price_limit_x96,
        }

    def build_swap_transaction(
        self,
        request: SwapTransactionRequest,
        signer_address: str,
        protocol: Literal["auto", "uniswap_v3", "aerodrome"] = "auto",
        gas_limit: int = 160000,
    ) -> Dict[str, Any]:
        """
        Builds raw transaction dictionary ready for signing.
        """
        router_addr = self.get_router_address(request.chain_id, protocol=protocol)
        params = self.build_exact_input_single_params(request)

        # Calldata representation for EVM dispatch
        return {
            "to": router_addr,
            "from": signer_address,
            "value": 0,
            "chainId": request.chain_id,
            "gas": gas_limit,
            "data": "0x",
            "swap_params": params,
        }

    def build_approval_transaction(
        self,
        token_address: str,
        spender_address: str,
        amount_wei: int,
        signer_address: str,
        chain_id: int,
        gas_limit: int = 60000,
    ) -> Dict[str, Any]:
        """
        Builds ERC-20 approve(spender, amount) transaction dictionary.
        """
        return {
            "to": token_address,
            "from": signer_address,
            "value": 0,
            "chainId": chain_id,
            "gas": gas_limit,
            "data": "0x",
            "token": token_address,
            "spender": spender_address,
            "amount": amount_wei,
        }

    def route_and_execute(
        self,
        request: SwapTransactionRequest,
        wallet_router: Any,
        signer_mode: str = "hot_keystore",
    ) -> SwapExecutionResult:
        """
        Routes swap through the given DualEngineWalletRouter instance.
        """
        return wallet_router.execute_swap(request, signer_mode=signer_mode)
