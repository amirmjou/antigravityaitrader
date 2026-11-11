"""
Adversarial Empirical Stress Test Suite for Arbitrum Uniswap v3 Execution,
Liquidity Depth, Slippage Scaling, and Gas Economics Claims.
Authored by challenger_m8_2 (Empirical Challenger Agent).

Covers:
1. Canonical contract verification: QuoterV2, Circle Native USDC, and typo rejections.
2. Empirical slippage scaling across sizes ($100 to $50k) on live Arbitrum RPC.
3. Multi-hop slippage reduction for LINK -> WETH -> USDC (70x - 220x reduction vs direct).
4. Gas economics under normal (0.02 Gwei), 10x spike (0.20 Gwei), and extreme 100x spike (2.0 Gwei).
5. Mathematical verification of breakeven trade size thresholds and Guardrail L4 bounds.
6. PreBroadcastGuardrailPipeline integration stress tests.
"""
import json
import urllib.request
import pytest
from web3 import Web3

from execution.guardrails.pipeline import PreBroadcastGuardrailPipeline
from tests.e2e.contracts import ChainExecutionConfig, SwapTransactionRequest, GuardrailVerdict
from tests.e2e.fixtures import MockWeb3Provider, MockGoPlusClient, MockUniswapV3Quoter


RPC_URL = "https://arb1.arbitrum.io/rpc"
QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
TYPO_QUOTER = "0x61fFE014bA136170505655d03170F09287640F16"
NATIVE_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
TYPO_USDC = "0xaf88d065e77c4c4779274291887c063473232247"
WETH = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
WBTC = "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f"
LINK = "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4"
ARB = "0x912CE59144191C1204E64559FE8253a0e49E6548"


def rpc_post(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        RPC_URL, data=body, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode())
    return res


# ===========================================================================
# 1. On-Chain Contract & Address Integrity Tests
# ===========================================================================

def test_canonical_quoter_v2_and_native_usdc_contracts():
    """Verify QuoterV2 and Native USDC on Arbitrum One; verify typo addresses have zero code."""
    # Check Canonical QuoterV2
    res = rpc_post("eth_getCode", [QUOTER_V2, "latest"])
    code = res.get("result", "")
    assert len(code) > 9000, f"Canonical QuoterV2 bytecode length {len(code)} is unexpectedly small."

    # Check Typo Quoter in codebase
    res_typo = rpc_post("eth_getCode", [TYPO_QUOTER, "latest"])
    assert res_typo.get("result") in ("0x", "0x0", None), "Typo Quoter should return 0 bytecode on Arbitrum One."

    # Check Circle Native USDC
    res_usdc = rpc_post("eth_getCode", [NATIVE_USDC, "latest"])
    code_usdc = res_usdc.get("result", "")
    assert len(code_usdc) > 1000, f"Native USDC contract length {len(code_usdc)} is invalid."

    # Check Typo USDC
    res_usdc_typo = rpc_post("eth_getCode", [TYPO_USDC, "latest"])
    assert res_usdc_typo.get("result") in ("0x", "0x0", None), "Typo USDC should return 0 bytecode."


# ===========================================================================
# 2. Empirical Slippage Scaling & Multi-Hop Reduction
# ===========================================================================

def test_empirical_slippage_scaling_and_multihop_reduction():
    """
    Adversarially benchmark QuoterV2 across sizes $100 to $50k.
    Asserts:
    1. Direct LINK->USDC slippage scales superlinearly and crosses excessive ticks.
    2. Multi-hop LINK->WETH->USDC reduces slippage dramatically (>50x reduction at >= $1k).
    """
    w3 = Web3()
    single_abi = [{
        "inputs": [{
            "components": [
                {"name": "tokenIn", "type": "address"},
                {"name": "tokenOut", "type": "address"},
                {"name": "amountIn", "type": "uint256"},
                {"name": "fee", "type": "uint24"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "params", "type": "tuple"
        }],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable", "type": "function"
    }]
    multi_abi = [{
        "inputs": [
            {"name": "path", "type": "bytes"},
            {"name": "amountIn", "type": "uint256"}
        ],
        "name": "quoteExactInput",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96AfterList", "type": "uint160[]"},
            {"name": "initializedTicksCrossedList", "type": "uint32[]"},
            {"name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable", "type": "function"
    }]
    contract = w3.eth.contract(address=QUOTER_V2, abi=single_abi + multi_abi)

    def call_single(amount_wei):
        cd = contract.encode_abi("quoteExactInputSingle", [(LINK, NATIVE_USDC, amount_wei, 3000, 0)])
        res = rpc_post("eth_call", [{"to": QUOTER_V2, "data": cd, "gas": "0x3000000"}, "latest"])
        assert "result" in res, f"RPC eth_call error: {res}"
        return w3.codec.decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(res["result"][2:]))

    def call_multi(amount_wei):
        path_bytes = bytes.fromhex(LINK[2:] + f"{3000:06x}" + WETH[2:] + f"{500:06x}" + NATIVE_USDC[2:])
        cd = contract.encode_abi("quoteExactInput", [path_bytes, amount_wei])
        res = rpc_post("eth_call", [{"to": QUOTER_V2, "data": cd, "gas": "0x3000000"}, "latest"])
        assert "result" in res, f"RPC eth_call error: {res}"
        return w3.codec.decode(["uint256", "uint160[]", "uint32[]", "uint256"], bytes.fromhex(res["result"][2:]))

    # Baseline 0.1 LINK marginal price
    base_direct = call_single(int(0.1 * 10**18))
    direct_unit_price = (base_direct[0] / 1e6) / 0.1

    base_multi = call_multi(int(0.1 * 10**18))
    multi_unit_price = (base_multi[0] / 1e6) / 0.1

    trade_sizes_usd = [100, 500, 1000, 5000, 10000, 50000]
    direct_slippages = []
    multi_slippages = []
    reductions = []

    for size in trade_sizes_usd:
        link_wei = int((size / direct_unit_price) * 10**18)
        d_out, _, d_ticks, _ = call_single(link_wei)
        m_out, _, m_ticks_list, _ = call_multi(link_wei)

        d_eff = (d_out / 1e6) / (link_wei / 1e18)
        d_slip = ((direct_unit_price - d_eff) / direct_unit_price) * 10000
        direct_slippages.append(d_slip)

        m_eff = (m_out / 1e6) / (link_wei / 1e18)
        m_slip = ((multi_unit_price - m_eff) / multi_unit_price) * 10000
        multi_slippages.append(m_slip)

        reduction = d_slip / m_slip
        reductions.append(reduction)

    # 1. Verify direct slippage strictly increases monotonically with trade size
    for i in range(len(direct_slippages) - 1):
        assert direct_slippages[i] < direct_slippages[i + 1], "Direct slippage must scale monotonically with size."

    # 2. Verify direct slippage crosses critical pain points
    assert direct_slippages[2] > 100.0, f"$1k direct slippage {direct_slippages[2]:.2f} bps should exceed 100 bps."
    assert direct_slippages[3] > 600.0, f"$5k direct slippage {direct_slippages[3]:.2f} bps should exceed 600 bps."
    assert direct_slippages[4] > 3000.0, f"$10k direct slippage {direct_slippages[4]:.2f} bps should exceed 3000 bps."
    assert direct_slippages[5] > 8000.0, f"$50k direct slippage {direct_slippages[5]:.2f} bps should exceed 8000 bps."

    # 3. Verify multi-hop slippage remains well controlled
    assert multi_slippages[2] < 5.0, f"$1k multi-hop slippage {multi_slippages[2]:.2f} bps should be < 5 bps."
    assert multi_slippages[4] < 30.0, f"$10k multi-hop slippage {multi_slippages[4]:.2f} bps should be < 30 bps."
    assert multi_slippages[5] < 150.0, f"$50k multi-hop slippage {multi_slippages[5]:.2f} bps should be < 150 bps."

    # 4. Verify multi-hop reduction factor across trade sizes ($1k to $50k)
    assert reductions[2] >= 50.0, f"$1k reduction {reductions[2]:.1f}x should be at least 50x."
    assert reductions[3] >= 50.0, f"$5k reduction {reductions[3]:.1f}x should be at least 50x."
    assert reductions[4] >= 150.0, f"$10k reduction {reductions[4]:.1f}x should be at least 150x."
    assert reductions[5] >= 50.0, f"$50k reduction {reductions[5]:.1f}x should be at least 50x."


# ===========================================================================
# 3. Gas Economics & Breakeven Threshold Mathematical Stress Tests
# ===========================================================================

def test_gas_cost_and_breakeven_trade_size_formulas():
    """
    Adversarially verify gas economics and breakeven trade size threshold formulas:
    - Normal (0.02 Gwei): gas cost $0.0056 (single-hop) / $0.0091 (multi-hop).
    - 10x Spike (0.20 Gwei): gas cost $0.0555 (single-hop) / $0.0904 (multi-hop).
    - Breakeven trade size formula: S_min = F_gas / (E[alpha] - fee - slippage).
    - Guardrail L4 ratio formula: S_guardrail = F_gas / 0.015.
    """
    eth_price = 2055.0
    gas_single = 135_000
    gas_multi = 220_000

    # Normal gas costs (0.0202 Gwei)
    base_fee_normal = 0.0202
    cost_single_normal = gas_single * base_fee_normal * 1e-9 * eth_price
    cost_multi_normal = gas_multi * base_fee_normal * 1e-9 * eth_price
    assert abs(cost_single_normal - 0.0056) < 0.0002
    assert abs(cost_multi_normal - 0.0091) < 0.0002

    # 10x Spike gas costs (0.202 Gwei)
    base_fee_10x = 0.202
    cost_single_10x = gas_single * base_fee_10x * 1e-9 * eth_price
    cost_multi_10x = gas_multi * base_fee_10x * 1e-9 * eth_price
    assert abs(cost_single_10x - 0.056) < 0.002
    assert abs(cost_multi_10x - 0.091) < 0.002

    # Case 1: Core WBTC/WETH Breakeven Trade Size
    # Expected alpha = 100 bps (0.01), fee = 5 bps (0.0005), slippage = 0.01 bps (0.000001)
    net_alpha_core = 0.0100 - 0.0005 - 0.000001
    s_min_core_normal = cost_single_normal / net_alpha_core
    s_min_core_10x = cost_single_10x / net_alpha_core

    assert abs(s_min_core_normal - 0.59) < 0.02, f"Normal Core breakeven {s_min_core_normal} != 0.59"
    assert abs(s_min_core_10x - 5.89) < 0.10, f"10x Core breakeven {s_min_core_10x} != 5.89"

    # Case 2: Satellite LINK Multi-Hop Breakeven Trade Size
    # Expected alpha = 100 bps (0.01), fee = 35 bps (0.0035), slippage = 1.7 bps (0.00017)
    net_alpha_link = 0.0100 - 0.0035 - 0.00017
    s_min_link_normal = cost_multi_normal / net_alpha_link
    s_min_link_10x = cost_multi_10x / net_alpha_link

    assert abs(s_min_link_normal - 1.44) < 0.05, f"Normal LINK breakeven {s_min_link_normal} != 1.44"
    assert abs(s_min_link_10x - 14.38) < 0.30, f"10x LINK breakeven {s_min_link_10x} != 14.38"

    # Case 3: Guardrail L4 Ratio Constraint (cost / S <= 1.5% = 0.015)
    s_guardrail_normal = cost_single_normal / 0.015
    s_guardrail_10x = cost_single_10x / 0.015
    s_guardrail_multi_10x = cost_multi_10x / 0.015

    assert abs(s_guardrail_normal - 0.37) < 0.02
    assert abs(s_guardrail_10x - 3.73) < 0.10
    assert abs(s_guardrail_multi_10x - 6.07) < 0.15

    # Rebalance chunking safety verification:
    # Architecture enforces minimum trade size of $50.00 and chunk size of $250.00.
    assert 50.0 > s_guardrail_multi_10x * 8.0, "Dust limit $50 provides >8x safety margin over 10x gas spike."
    assert 250.0 > s_guardrail_multi_10x * 40.0, "Chunk limit $250 provides >40x safety margin over 10x gas spike."


# ===========================================================================
# 4. PreBroadcastGuardrailPipeline Gas Spike Stress Test
# ===========================================================================

def test_guardrail_pipeline_under_gas_spikes():
    """
    Stress-test PreBroadcastGuardrailPipeline under normal, 10x spike, 100x spike,
    and gas ceiling breach conditions.
    """
    arb_config = ChainExecutionConfig(
        chain_id=42161,
        chain_name="Arbitrum One",
        rpc_url="https://arb1.arbitrum.io/rpc",
        router_address="0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        quoter_address=QUOTER_V2,
        default_slippage_bps=50,
        max_slippage_bps=100,
        gas_ceiling_gwei=120.0,
        gas_cost_ratio_max_pct=1.5,
    )
    quoter = MockUniswapV3Quoter(base_price_usd=2055.0, pool_liquidity_usd=50000000.0)

    def create_pipeline(base_fee: float):
        prov = MockWeb3Provider(chain_id=42161, base_fee_gwei=base_fee)
        prov.priority_fee_gwei = 0.005  # Arbitrum standard priority fee
        return PreBroadcastGuardrailPipeline(
            chain_config=arb_config,
            web3_provider=prov,
            goplus_client=MockGoPlusClient(),
            quoter=quoter,
            max_spend_per_trade_usd=250.0,
            max_asset_concentration_pct=20.0,
            max_daily_drawdown_pct=8.0,
            eth_price_usd=2055.0,
        )

    def make_tx(val_usd: float, fee_gwei: float):
        return SwapTransactionRequest(
            chain_id=42161,
            router_address=arb_config.router_address,
            token_in=WETH,
            token_out=NATIVE_USDC,
            recipient="0x1111111111111111111111111111111111111111",
            amount_in_wei=int((val_usd / 2055.0) * 10**18),
            amount_out_min_wei=int(val_usd * 0.995 * 10**6),
            trade_value_usd=val_usd,
            portfolio_value_usd=1000.0,
            current_asset_holding_usd=0.0,
            daily_drawdown_pct=0.0,
            gas_limit=135000,
            max_fee_per_gas_gwei=fee_gwei,
            max_priority_fee_per_gas_gwei=0.005,
            deadline_seconds=120,
        )

    # Normal gas: 0.02 Gwei
    pipe_normal = create_pipeline(0.02)
    assert pipe_normal.evaluate(make_tx(50.0, 0.025)).approved is True
    assert pipe_normal.evaluate(make_tx(250.0, 0.025)).approved is True

    # 10x Spike: 0.20 Gwei
    pipe_10x = create_pipeline(0.20)
    assert pipe_10x.evaluate(make_tx(50.0, 0.25)).approved is True
    assert pipe_10x.evaluate(make_tx(250.0, 0.25)).approved is True
    # Sub-$3 micro-order should trip Layer 4 under 10x spike
    res_micro = pipe_10x.evaluate(make_tx(2.0, 0.25))
    assert res_micro.approved is False
    assert "Layer 4 Gas-to-trade ratio" in res_micro.rejection_reason

    # Extreme 100x Spike: 2.0 Gwei
    pipe_100x = create_pipeline(2.0)
    # $50 trade trips L4 (gas ~$0.60 / $50 = 1.2% - let's check exact)
    # simulated gas 145000 * 2.005e-9 * 2055 = $0.5975 USD -> 0.5975 / 50 = 1.19% (passes <1.5%)
    # $20 trade trips L4 (0.5975 / 20 = 2.99% > 1.5%)
    res_20 = pipe_100x.evaluate(make_tx(20.0, 2.5))
    assert res_20.approved is False
    assert "Layer 4 Gas-to-trade ratio" in res_20.rejection_reason

    # Gas ceiling breach: 125.0 Gwei (> 120.0 Gwei ceiling)
    pipe_breach = create_pipeline(125.0)
    res_breach = pipe_breach.evaluate(make_tx(250.0, 130.0))
    assert res_breach.approved is False
    assert "exceeds ceiling 120.0 gwei" in res_breach.rejection_reason
