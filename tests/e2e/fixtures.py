"""
High-fidelity Deterministic Mocks and Fixtures for E2E Testing.
Provides offline simulation for Web3 RPCs, GoPlus Security, CCXT Exchanges,
Alternative.me, DeFiLlama, Gemini/Antigravity, and Jev MCP.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. Mock Web3 RPC Provider (Arbitrum & Base)
# ---------------------------------------------------------------------------

class MockWeb3Provider:
    """Simulates an EVM RPC node supporting Arbitrum One (42161) and Base (8453)."""

    def __init__(self, chain_id: int = 42161, base_fee_gwei: float = 0.1):
        self.chain_id = chain_id
        self.block_number = 270000000
        self.base_fee_gwei = base_fee_gwei
        self.priority_fee_gwei = 0.05
        self.balances: Dict[str, int] = {
            "0xUserWallet": 10 * 10**18,  # 10 ETH
            "0xHotSigner": 1 * 10**18,    # 1 ETH
        }
        self.revert_trigger: Optional[str] = None
        self.simulated_gas: int = 145000
        self.tx_history: List[Dict[str, Any]] = []

    def set_revert_trigger(self, reason: Optional[str]):
        self.revert_trigger = reason

    def get_block_number(self) -> int:
        self.block_number += 1
        return self.block_number

    def get_balance(self, address: str) -> int:
        return self.balances.get(address, 0)

    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        if self.revert_trigger:
            raise RuntimeError(f"execution reverted: {self.revert_trigger}")
        return self.simulated_gas

    def eth_call(self, tx_params: Dict[str, Any]) -> bytes:
        """Simulates eth_call pre-flight dry run."""
        if self.revert_trigger:
            raise RuntimeError(f"execution reverted: {self.revert_trigger}")
        # Return dummy 32-byte success output (e.g. amount out)
        amount_out = tx_params.get("amount_out_min", 95000000)
        return amount_out.to_bytes(32, byteorder="big")

    def send_raw_transaction(self, raw_tx_hex: str) -> str:
        if self.revert_trigger:
            raise RuntimeError(f"execution reverted: {self.revert_trigger}")
        tx_hash = "0x" + hashlib.sha256(raw_tx_hex.encode()).hexdigest()
        self.tx_history.append({
            "tx_hash": tx_hash,
            "raw_tx": raw_tx_hex,
            "block_number": self.get_block_number(),
            "timestamp": int(time.time()),
        })
        return tx_hash


# ---------------------------------------------------------------------------
# 2. Mock GoPlus Security API
# ---------------------------------------------------------------------------

class MockGoPlusClient:
    """Simulates GoPlus Token Security API for honeypot and malicious contract detection."""

    def __init__(self):
        self.token_database: Dict[str, Dict[str, Any]] = {
            # Standard Safe Tokens (WETH, WBTC, USDC)
            "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1": {  # WETH on Arb
                "is_honeypot": "0",
                "buy_tax": "0.0",
                "sell_tax": "0.0",
                "is_mintable": "0",
                "is_open_source": "1",
                "cannot_sell_all": "0",
            },
            "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f": {  # WBTC on Arb
                "is_honeypot": "0",
                "buy_tax": "0.0",
                "sell_tax": "0.0",
                "is_mintable": "0",
                "is_open_source": "1",
                "cannot_sell_all": "0",
            },
            # Malicious / Honeypot Token
            "0xBadHoneypotTokenAddress0000000000000000": {
                "is_honeypot": "1",
                "buy_tax": "0.10",
                "sell_tax": "0.99",
                "is_mintable": "1",
                "is_open_source": "0",
                "cannot_sell_all": "1",
            },
            # High Tax Token (3% tax > 1% limit)
            "0xHighTaxTokenAddress0000000000000000000": {
                "is_honeypot": "0",
                "buy_tax": "0.03",
                "sell_tax": "0.03",
                "is_mintable": "0",
                "is_open_source": "1",
                "cannot_sell_all": "0",
            },
        }

    def check_token_security(self, chain_id: int, token_address: str) -> Dict[str, Any]:
        token_data = self.token_database.get(token_address)
        if not token_data:
            # Default to unknown but safe
            return {
                "is_honeypot": "0",
                "buy_tax": "0.0",
                "sell_tax": "0.0",
                "is_mintable": "0",
                "is_open_source": "1",
                "cannot_sell_all": "0",
            }
        return token_data


# ---------------------------------------------------------------------------
# 3. Mock Uniswap v3 Quoter (IQuoterV2)
# ---------------------------------------------------------------------------

class MockUniswapV3Quoter:
    """Simulates off-chain quote calculations via Uniswap v3 IQuoterV2."""

    def __init__(self, base_price_usd: float = 88500.0, pool_liquidity_usd: float = 50000000.0):
        self.base_price_usd = base_price_usd
        self.pool_liquidity_usd = pool_liquidity_usd

    def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        fee_tier: int = 500,
    ) -> Tuple[int, float, int]:
        """
        Returns (amount_out_wei, price_impact_pct, gas_estimate).
        Price impact is modeled proportionally to trade_size / pool_liquidity.
        """
        trade_usd = (amount_in_wei / 10**18) * self.base_price_usd
        price_impact_pct = (trade_usd / self.pool_liquidity_usd) * 100.0
        
        # Calculate amount out accounting for price impact & fee tier (e.g. 0.05%)
        fee_pct = fee_tier / 1000000.0
        effective_rate = (1.0 - (price_impact_pct / 100.0) - fee_pct)
        amount_out_wei = int(amount_in_wei * effective_rate)
        gas_estimate = 125000
        return (amount_out_wei, price_impact_pct, gas_estimate)


# ---------------------------------------------------------------------------
# 4. Mock CCXT Multi-Exchange Client
# ---------------------------------------------------------------------------

class MockCCXTExchange:
    """Simulates CCXT Exchange (Binance/Coinbase) with precision lot formatting."""

    def __init__(self, exchange_id: str = "binance"):
        self.id = exchange_id
        self.rateLimit = 1000
        self.enableRateLimit = True
        self.market_prices: Dict[str, float] = {
            "BTC/USDT": 88500.0,
            "ETH/USDT": 3100.0,
            "SOL/USDT": 185.0,
        }
        self.precisions: Dict[str, int] = {
            "BTC/USDT": 5,  # 0.00001 BTC
            "ETH/USDT": 4,  # 0.0001 ETH
            "SOL/USDT": 2,  # 0.01 SOL
        }

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        price = self.market_prices.get(symbol, 100.0)
        return {
            "symbol": symbol,
            "last": price,
            "bid": price * 0.9998,
            "ask": price * 1.0002,
            "close": price,
            "timestamp": int(time.time() * 1000),
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 14) -> List[List[float]]:
        base_price = self.market_prices.get(symbol, 100.0)
        now_ms = int(time.time() * 1000)
        candles = []
        for i in range(limit):
            t = now_ms - (limit - i) * 3600 * 1000
            o = base_price * (1.0 + (i * 0.002))
            h = o * 1.01
            l = o * 0.99
            c = o * 1.005
            v = 1500.0
            candles.append([t, o, h, l, c, v])
        return candles

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        prec = self.precisions.get(symbol, 4)
        factor = 10**prec
        truncated = math.floor(amount * factor) / factor
        return f"{truncated:.{prec}f}"


# ---------------------------------------------------------------------------
# 5. Mock Public Sentiment & Macro APIs (Alternative.me & DeFiLlama)
# ---------------------------------------------------------------------------

class MockPublicAPIs:
    """Simulates Alternative.me Fear & Greed and DeFiLlama chain TVL."""

    @staticmethod
    def get_fear_and_greed(override_value: Optional[int] = None) -> Dict[str, Any]:
        val = override_value if override_value is not None else 68
        classification = "Greed" if val >= 55 else ("Extreme Greed" if val >= 75 else ("Fear" if val >= 25 else "Extreme Fear"))
        return {
            "name": "Crypto Fear & Greed Index",
            "data": [
                {
                    "value": str(val),
                    "value_classification": classification,
                    "timestamp": str(int(time.time())),
                }
            ],
        }

    @staticmethod
    def get_defillama_chains() -> List[Dict[str, Any]]:
        return [
            {"name": "Ethereum", "tvl": 58000000000.0, "tokenSymbol": "ETH"},
            {"name": "Arbitrum", "tvl": 3200000000.0, "tokenSymbol": "ARB"},
            {"name": "Base", "tvl": 1600000000.0, "tokenSymbol": "BASE"},
            {"name": "Solana", "tvl": 6800000000.0, "tokenSymbol": "SOL"},
        ]


# ---------------------------------------------------------------------------
# 6. Mock Gemini & Google Antigravity SDK LLM Client
# ---------------------------------------------------------------------------

class MockGeminiAntigravityClient:
    """Simulates NormalizedChatGoogleGenerativeAI with thinking levels."""

    def __init__(self, thinking_level: str = "high"):
        self.thinking_level = thinking_level
        self.call_history: List[Dict[str, Any]] = []

    def invoke(self, prompt: str, schema: Optional[Any] = None) -> Any:
        self.call_history.append({"prompt": prompt, "schema": schema, "level": self.thinking_level})
        
        # If schema is provided, return structured mock matching the schema
        if schema and hasattr(schema, "__name__"):
            name = schema.__name__
            if name == "TraderProposal":
                from tests.e2e.contracts import TraderAction, TraderProposal
                return TraderProposal(
                    action=TraderAction.BUY.value,
                    reasoning="High probability breakout confirmed by market and sentiment analysts.",
                    entry_price=88500.0,
                    stop_loss=86500.0,
                    position_sizing="5% of portfolio",
                    symbol="BTC-USD",
                )
            elif name == "PortfolioDecision":
                from tests.e2e.contracts import PortfolioDecision, PortfolioRating
                return PortfolioDecision(
                    rating=PortfolioRating.BUY.value,
                    executive_summary="Execute phased long entry on BTC-USD with tight stop below support.",
                    investment_thesis="Bullish divergence across multi-timeframe indicators supported by macro liquidity.",
                    price_target=95000.0,
                    time_horizon="2-4 weeks",
                )
            elif name == "ResearchPlan":
                from tests.e2e.contracts import PortfolioRating, ResearchPlan
                return ResearchPlan(
                    recommendation=PortfolioRating.BUY,
                    rationale="Bull thesis decisively won the debate on network hash rate and ETF inflows.",
                    strategic_actions="Establish initial long position, allocate 5% risk budget.",
                )
        
        # Default text response
        return "Deliberation complete: Strong institutional conviction supports strategic capital allocation."


# ---------------------------------------------------------------------------
# 7. Local Jev MCP Engine Adapter
# ---------------------------------------------------------------------------

class LocalJevMCPClient:
    """Interfaces with the local Jev MCP engine with offline heuristic fallback."""

    def __init__(self):
        self.mode = "on-premise-offline"

    def decide(self, state: Dict[str, Any], questions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Executes deterministic offline heuristic evaluation."""
        state_str = json.dumps(state)
        results = {}
        for q_id, q_spec in questions.items():
            q_type = q_spec.get("type", "choice")
            criteria = q_spec.get("criteria", {})
            
            if q_type == "choice":
                # Deterministic scoring based on state properties
                drawdown = state.get("drawdown", 0.0)
                risk_limit = state.get("risk_limit", 0.08)
                if drawdown > risk_limit:
                    choice = "REJECT"
                else:
                    choice = "APPROVE"
                results[q_id] = {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 0.85,
                    "probabilities": {"APPROVE": 0.85 if choice == "APPROVE" else 0.15, "REJECT": 0.15 if choice == "APPROVE" else 0.85}
                }
            elif q_type == "noul":
                results[q_id] = {"type": "noul", "noul": True, "probability": 0.78, "confidence": 0.82}
            elif q_type == "score":
                results[q_id] = {"type": "score", "score": "Good", "confidence": 0.70}
        return results

    def pick_variant(self, brief: str, variants: Dict[str, str]) -> Dict[str, Any]:
        """Picks the highest scoring variant."""
        best_key = next(iter(variants.keys())) if variants else "default"
        return {
            "best_variant": {
                "type": "choice",
                "choice": best_key,
                "confidence": 0.65,
                "probabilities": {k: 1.0 / len(variants) for k in variants}
            }
        }

    def review_design(self, brief: str, design_summary: str) -> Dict[str, Any]:
        """Evaluates UI quality gate metrics."""
        return {
            "brand_fit": {"type": "score", "score": "Good", "confidence": 0.7},
            "visual_quality": {"type": "score", "score": "Good", "confidence": 0.75},
            "clarity": {"type": "score", "score": "Good", "confidence": 0.72},
            "cta_strength": {"type": "score", "score": "Good", "confidence": 0.68},
            "ready_to_ship": {"type": "noul", "noul": True, "probability": 0.80, "confidence": 0.85},
            "next_focus": {"type": "choice", "choice": "none", "confidence": 0.40}
        }


# ---------------------------------------------------------------------------
# 8. Mock Remote Agent CLI Bridge (agy --remote-agent)
# ---------------------------------------------------------------------------

class MockRemoteAgentBridge:
    """Simulates non-interactive agy --remote-agent cloud VM execution."""

    def __init__(self, should_fail: bool = False, failure_mode: Optional[str] = None):
        self.should_fail = should_fail
        self.failure_mode = failure_mode

    def run_remote_deliberation(self, symbol: str, prompt: str) -> Tuple[int, str, str]:
        """
        Returns (exit_code, stdout_json, stderr_logs).
        """
        if self.should_fail:
            if self.failure_mode == "timeout":
                return (124, "", "Error: remote agent execution timed out after 120s")
            elif self.failure_mode == "malformed_json":
                return (0, "{invalid_json_stream...", "Warning: partial output emitted")
            else:
                return (1, "", "Error: Cloud VM allocation quota exceeded")
        
        payload = {
            "turn_count": 6,
            "duration_ms": 3450,
            "token_usage": {"prompt": 1240, "completion": 480, "total": 1720},
            "response": {
                "symbol": symbol,
                "rating": "Buy",
                "bull_argument": f"Institutional momentum on {symbol} supported by high spot ETF net inflows.",
                "bear_argument": f"Short-term overbought RSI requires tight trailing stop.",
                "risk_assessment": "Moderate market volatility within standard ATR boundaries.",
                "position_size_usd": 200.0,
                "stop_loss_pct": 2.5,
                "entry_target_usd": 88500.0 if "BTC" in symbol else (3100.0 if "ETH" in symbol else 185.0),
            }
        }
        stdout = json.dumps(payload)
        stderr = "INFO: Antigravity remote agent initialized. Cloud VM ready.\nINFO: Completed in 3450ms."
        return (0, stdout, stderr)
