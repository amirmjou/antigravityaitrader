"""Simulated Exchange Order Matching & Portfolio Ledger Engine (Feature F24).

Supports:
- Buy and Sell order placement against virtual cash and asset inventory
- Weighted-average entry price calculation on cumulative buys
- Realized and unrealized PnL tracking
- Strict rejection of non-positive or non-finite quantities/prices
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, List

from tests.e2e.contracts import PaperTradingOrder, PaperTradingPosition


class PaperTradingEngine:
    """Thread-safe simulated exchange order matching and portfolio book."""

    def __init__(self, initial_cash_usd: float = 10000.0):
        if not math.isfinite(initial_cash_usd) or initial_cash_usd < 0:
            raise ValueError(f"Invalid initial_cash_usd: {initial_cash_usd}")
        self.initial_cash_usd = float(initial_cash_usd)
        self.cash_usd = float(initial_cash_usd)
        self.positions: Dict[str, PaperTradingPosition] = {}
        self.orders: List[PaperTradingOrder] = []
        self._lock = threading.Lock()

    def place_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> PaperTradingOrder:
        """Place and match a simulated Buy or Sell order."""
        if not math.isfinite(quantity) or not math.isfinite(price):
            raise ValueError("Order quantity and price must be finite numbers")
        if side not in ("Buy", "Sell"):
            raise ValueError(f"Invalid order side: {side}")

        with self._lock:
            order = PaperTradingOrder(
                order_id=f"order_{len(self.orders) + 1}",
                symbol=symbol,
                side=side,  # type: ignore
                quantity=quantity,
                price=price,
                timestamp_ms=int(time.time() * 1000),
                status="pending",
            )

            # Reject non-positive quantities or prices cleanly without mutating ledger
            if quantity <= 0.0 or price <= 0.0:
                order.status = "rejected"
                self.orders.append(order)
                return order

            order_cost = quantity * price

            if side == "Buy":
                if order_cost > self.cash_usd:
                    order.status = "rejected"
                else:
                    self.cash_usd -= order_cost
                    order.status = "filled"
                    pos = self.positions.get(symbol)
                    if not pos or pos.quantity == 0.0:
                        realized = pos.realized_pnl_usd if pos else 0.0
                        self.positions[symbol] = PaperTradingPosition(
                            symbol=symbol,
                            quantity=quantity,
                            average_entry_price=price,
                            current_market_price=price,
                            unrealized_pnl_usd=0.0,
                            realized_pnl_usd=realized,
                        )
                    else:
                        new_qty = pos.quantity + quantity
                        pos.average_entry_price = (
                            (pos.quantity * pos.average_entry_price) + order_cost
                        ) / new_qty
                        pos.quantity = new_qty
                        pos.current_market_price = price
                        pos.unrealized_pnl_usd = (
                            price - pos.average_entry_price
                        ) * pos.quantity
            elif side == "Sell":
                pos = self.positions.get(symbol)
                if not pos or pos.quantity < quantity:
                    order.status = "rejected"
                else:
                    realized_gain = (price - pos.average_entry_price) * quantity
                    pos.realized_pnl_usd += realized_gain
                    pos.quantity -= quantity
                    pos.current_market_price = price
                    pos.unrealized_pnl_usd = (
                        (price - pos.average_entry_price) * pos.quantity
                        if pos.quantity > 0
                        else 0.0
                    )
                    self.cash_usd += order_cost
                    order.status = "filled"

            self.orders.append(order)
            return order

    def mark_to_market(self, symbol: str, market_price: float) -> float:
        """Update current market price for a held position and return unrealized PnL."""
        if not math.isfinite(market_price) or market_price <= 0:
            raise ValueError(f"Invalid market_price: {market_price}")
        with self._lock:
            pos = self.positions.get(symbol)
            if not pos:
                return 0.0
            pos.current_market_price = market_price
            pos.unrealized_pnl_usd = (market_price - pos.average_entry_price) * pos.quantity
            return pos.unrealized_pnl_usd

    def total_portfolio_value_usd(self) -> float:
        """Return total cash + mark-to-market value of all open positions."""
        with self._lock:
            holdings_val = sum(
                pos.quantity * pos.current_market_price for pos in self.positions.values()
            )
            return self.cash_usd + holdings_val
