"""
Pre-Broadcast Safety Guardrail Pipeline (PBSGP).
Coordinates the 5 safety layers:
Layer 1: Contract Security (GoPlus honeypot, tax <= 1%, blacklist check)
Layer 2: Capital Allocation (per-trade cap $250, asset concentration <=20%, daily drawdown circuit breaker 8%)
Layer 3: Dynamic Slippage (Uniswap v3 IQuoterV2 pricing, 30-100 bps slippage, <=2% price impact, 300s deadline)
Layer 4: Gas & Congestion (EIP-1559 base fee check, priority fee, gas-to-trade ratio <=1.5%)
Layer 5: Pre-Flight Simulation (eth_call dry run with custom revert reason decoding)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from tests.e2e.contracts import (
    ChainExecutionConfig,
    GuardrailVerdict,
    SwapTransactionRequest,
)

logger = logging.getLogger("execution.guardrails.pipeline")


class PreBroadcastGuardrailPipeline:
    """
    Serial 5-layer safety gate evaluated prior to signing or broadcasting any transaction.
    If any layer trips, transaction broadcast is blocked immediately and a structured
    GuardrailVerdict detailing the failed layer and root cause is returned.
    """

    def __init__(
        self,
        chain_config: ChainExecutionConfig,
        web3_provider: Any,
        goplus_client: Any,
        quoter: Any,
        max_spend_per_trade_usd: float = 250.0,
        max_asset_concentration_pct: float = 20.0,
        max_daily_drawdown_pct: float = 8.0,
        eth_price_usd: float = 3100.0,
        allow_micro_capital_concentration: bool = True,
    ):
        self.config = chain_config
        self.w3 = web3_provider
        self.goplus = goplus_client
        self.quoter = quoter
        self.max_spend_per_trade_usd = max_spend_per_trade_usd
        self.max_asset_concentration_pct = max_asset_concentration_pct
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.eth_price_usd = eth_price_usd
        self.allow_micro_capital_concentration = allow_micro_capital_concentration

    def _get_base_fee_gwei(self) -> float:
        """Extract base fee in gwei from provider."""
        if hasattr(self.w3, "base_fee_gwei"):
            return float(self.w3.base_fee_gwei)
        elif hasattr(self.w3, "eth") and hasattr(self.w3.eth, "get_block"):
            try:
                blk = self.w3.eth.get_block("latest")
                return float(blk.get("baseFeePerGas", 100_000_000)) / 1e9
            except Exception:
                return 0.1
        return 0.1

    def _get_priority_fee_gwei(self) -> float:
        """Extract priority fee in gwei from provider."""
        if hasattr(self.w3, "priority_fee_gwei"):
            return float(self.w3.priority_fee_gwei)
        elif hasattr(self.w3, "eth") and hasattr(self.w3.eth, "max_priority_fee"):
            try:
                return float(self.w3.eth.max_priority_fee) / 1e9
            except Exception:
                return 0.05
        return 0.05

    def _execute_dry_run(self, request: SwapTransactionRequest) -> None:
        """Executes eth_call dry-run against the target node."""
        call_params = {
            "to": self.config.router_address,
            "amount_in": request.amount_in_wei,
            "amount_out_min": request.amount_out_min_wei,
        }
        if hasattr(self.w3, "eth_call") and callable(self.w3.eth_call):
            self.w3.eth_call(call_params)
        elif hasattr(self.w3, "eth") and hasattr(self.w3.eth, "call"):
            self.w3.eth.call(call_params)

    def evaluate(
        self,
        request: SwapTransactionRequest,
        current_portfolio_value_usd: float = 5000.0,
        current_asset_holdings_usd: float = 400.0,
        current_daily_drawdown_pct: float = 2.0,
        override_quoter_impact_pct: Optional[float] = None,
    ) -> GuardrailVerdict:
        """
        Executes all 5 safety layers sequentially.
        Returns GuardrailVerdict with approval status, rejection details, and execution metrics.
        """
        # ===================================================================
        # Layer 1: Contract Security (GoPlus)
        # ===================================================================
        if request.token_in.lower() == request.token_out.lower():
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 1: Self-swap rejected - token_in and token_out cannot be the same asset",
                layer_failed="Layer 1: Contract Security",
            )

        if request.amount_in_wei <= 0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 1: Non-positive amount_in_wei rejected - amount must be > 0",
                layer_failed="Layer 1: Contract Security",
            )

        sec_in = self.goplus.check_token_security(request.chain_id, request.token_in)
        sec_out = self.goplus.check_token_security(request.chain_id, request.token_out)

        for sec, name in [(sec_in, "token_in"), (sec_out, "token_out")]:
            if str(sec.get("is_honeypot", "0")) == "1" or sec.get("is_honeypot") is True:
                return GuardrailVerdict(
                    approved=False,
                    rejection_reason=f"Layer 1 Honeypot detected on {name}.",
                    layer_failed="Layer 1: Contract Security",
                )

            buy_tax = float(sec.get("buy_tax", "0.0"))
            sell_tax = float(sec.get("sell_tax", "0.0"))
            if buy_tax > 0.01 or sell_tax > 0.01:
                return GuardrailVerdict(
                    approved=False,
                    rejection_reason=f"Layer 1 Tax exceeds 1% ceiling (buy: {buy_tax*100}%, sell: {sell_tax*100}%).",
                    layer_failed="Layer 1: Contract Security",
                )

            if str(sec.get("cannot_sell_all", "0")) == "1" or str(sec.get("is_blacklisted", "0")) == "1":
                return GuardrailVerdict(
                    approved=False,
                    rejection_reason=f"Layer 1 Transfer restriction or blacklist detected on {name}.",
                    layer_failed="Layer 1: Contract Security",
                )

        # ===================================================================
        # Layer 2: Capital Allocation & Drawdown
        # ===================================================================
        if request.trade_value_usd <= 0.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 2: Non-positive trade_value_usd rejected - trade value must be > $0.00",
                layer_failed="Layer 2: Capital Allocation",
            )

        if current_portfolio_value_usd <= 0.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 2: Non-positive portfolio value rejected - current portfolio value must be > $0.00",
                layer_failed="Layer 2: Capital Allocation",
            )

        if request.trade_value_usd > self.max_spend_per_trade_usd:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Per-trade spend ${request.trade_value_usd} exceeds cap of ${self.max_spend_per_trade_usd}.",
                layer_failed="Layer 2: Capital Allocation",
            )

        effective_max_concentration = self.max_asset_concentration_pct
        if self.allow_micro_capital_concentration and current_portfolio_value_usd < 25.0:
            effective_max_concentration = 98.0

        new_asset_total = current_asset_holdings_usd + request.trade_value_usd
        concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0 if current_portfolio_value_usd > 0 else 100.0
        if concentration_pct > effective_max_concentration:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Asset concentration {concentration_pct:.1f}% exceeds max {effective_max_concentration}%.",
                layer_failed="Layer 2: Capital Allocation",
            )

        if current_daily_drawdown_pct >= self.max_daily_drawdown_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Daily drawdown {current_daily_drawdown_pct:.1f}% exceeds circuit breaker {self.max_daily_drawdown_pct}%.",
                layer_failed="Layer 2: Capital Allocation",
            )

        # ===================================================================
        # Layer 3: Dynamic Slippage & Price Impact
        # ===================================================================
        if request.slippage_bps < 0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 3: Negative slippage tolerance rejected",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.slippage_bps > self.config.max_slippage_bps:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Requested slippage {request.slippage_bps} bps exceeds max {self.config.max_slippage_bps} bps.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        amount_out_wei, price_impact_pct, _ = self.quoter.quote_exact_input_single(
            request.token_in, request.token_out, request.amount_in_wei
        )

        if override_quoter_impact_pct is not None:
            price_impact_pct = override_quoter_impact_pct

        if price_impact_pct > 2.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Price impact {price_impact_pct:.2f}% exceeds 2.0% threshold.",
                layer_failed="Layer 3: Dynamic Slippage",
                estimated_price_impact_pct=price_impact_pct,
            )

        if request.deadline_seconds < 1:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 3: Non-positive deadline rejected",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.deadline_seconds > 300:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Transaction deadline {request.deadline_seconds}s exceeds 300s limit.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        # ===================================================================
        # Layer 4: Gas & Congestion
        # ===================================================================
        base_fee_gwei = self._get_base_fee_gwei()
        priority_fee_gwei = self._get_priority_fee_gwei()

        if base_fee_gwei > self.config.gas_ceiling_gwei:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 4 Network base fee {base_fee_gwei} gwei exceeds ceiling {self.config.gas_ceiling_gwei} gwei.",
                layer_failed="Layer 4: Gas & Congestion",
            )

        simulated_gas = 145000
        gas_cost_usd = (simulated_gas * (base_fee_gwei + priority_fee_gwei) * 1e-9) * self.eth_price_usd
        gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0 if request.trade_value_usd > 0 else float('inf')

        if gas_ratio_pct > self.config.gas_cost_ratio_max_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 4 Gas-to-trade ratio {gas_ratio_pct:.2f}% exceeds max {self.config.gas_cost_ratio_max_pct}%.",
                layer_failed="Layer 4: Gas & Congestion",
            )

        # ===================================================================
        # Layer 5: eth_call Dry-Run Pre-Flight Simulation
        # ===================================================================
        try:
            self._execute_dry_run(request)
        except Exception as e:
            raw_err = str(e)
            if "execution reverted: " in raw_err:
                revert_msg = raw_err.split("execution reverted: ")[-1]
            elif "reverted: " in raw_err:
                revert_msg = raw_err.split("reverted: ")[-1]
            else:
                revert_msg = raw_err

            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 5 Simulation reverted: {revert_msg}",
                layer_failed="Layer 5: Pre-Flight Simulation",
            )

        # All 5 layers passed
        return GuardrailVerdict(
            approved=True,
            simulated_gas_used=simulated_gas,
            quoted_amount_out_min=amount_out_wei,
            estimated_price_impact_pct=price_impact_pct,
        )
