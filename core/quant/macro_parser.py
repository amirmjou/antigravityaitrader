"""Macro Data & Catalyst Parser for the Antigravity Quantitative Execution Loop.

Parses macroeconomic indicators (CPI YoY, Fed Funds Rate, US 10Y Treasury Yield,
VIX Volatility Index, DXY Dollar Index) and corporate/regulatory catalysts
(Earnings dates, FDA PDUFA dates, Government contract awards) into structured
regime multipliers and risk scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CatalystEvent:
    """Structured representation of an upcoming stock or macro catalyst."""

    date: str
    event_type: str  # "EARNINGS", "FDA_PDUFA", "GOV_CONTRACT", "MACRO_FOMC", "PRODUCT"
    description: str
    certainty: str  # "HIGH", "MEDIUM", "LOW"
    source: str
    clarity_score: float  # 0.0 to 10.0 per risk-score.md


@dataclass(frozen=True)
class MacroRegimeSnapshot:
    """Macroeconomic regime snapshot parsed from macro data feeds or raw text."""

    cpi_yoy_pct: float
    fed_funds_rate_pct: float
    us10y_yield_pct: float
    vix_index: float
    dxy_index: float
    macro_regime: str  # "RISK_ON", "NEUTRAL", "RISK_OFF_HAWKISH", "VOL_SHOCK"
    position_size_multiplier: float  # 0.25 to 1.25
    summary: str
    catalysts: List[CatalystEvent] = field(default_factory=list)


class MacroDataParser:
    """Parses structured dicts or unstructured financial text into MacroRegimeSnapshot & CatalystEvents."""

    _DATE_RE = re.compile(r"\b(202[5-9]-[01]\d-[0-3]\d)\b")
    _QUARTER_RE = re.compile(r"\b(202[5-9]\s*Q[1-4]|Q[1-4]\s*202[5-9]|202[5-9]\s*H[1-2])\b", re.IGNORECASE)

    def parse_macro_payload(
        self,
        payload: Optional[Dict[str, Any]] = None,
        raw_text: str = "",
    ) -> MacroRegimeSnapshot:
        """Parse macroeconomic telemetry dict and/or raw text into a MacroRegimeSnapshot."""
        data = dict(payload or {})

        cpi = float(data.get("cpi_yoy_pct", self._extract_float(raw_text, r"CPI[^\d]*(\d+\.\d+)%", 2.6)))
        fed = float(data.get("fed_funds_rate_pct", self._extract_float(raw_text, r"Fed Funds[^\d]*(\d+\.\d+)%", 4.50)))
        us10y = float(data.get("us10y_yield_pct", self._extract_float(raw_text, r"10Y[^\d]*(\d+\.\d+)%", 4.25)))
        vix = float(data.get("vix_index", self._extract_float(raw_text, r"VIX[^\d]*(\d+\.\d+)", 16.5)))
        dxy = float(data.get("dxy_index", self._extract_float(raw_text, r"DXY[^\d]*(\d+\.\d+)", 103.8)))

        if vix >= 30.0:
            regime = "VOL_SHOCK"
            mult = 0.40
            summary = f"High volatility shock (VIX={vix:.1f}); de-risking exposure to 40%."
        elif cpi >= 4.0 or us10y >= 4.85 or vix >= 23.0:
            regime = "RISK_OFF_HAWKISH"
            mult = 0.65
            summary = f"Hawkish/tightening macro pressure (CPI={cpi:.1f}%, 10Y={us10y:.2f}%, VIX={vix:.1f})."
        elif cpi <= 3.0 and vix < 18.0 and us10y < 4.50:
            regime = "RISK_ON"
            mult = 1.10
            summary = f"Constructive risk-on macro backdrop (CPI={cpi:.1f}%, VIX={vix:.1f}, 10Y={us10y:.2f}%)."
        else:
            regime = "NEUTRAL"
            mult = 1.00
            summary = f"Neutral macro regime (CPI={cpi:.1f}%, Fed={fed:.2f}%, 10Y={us10y:.2f}%, VIX={vix:.1f})."

        catalysts = self.parse_catalysts(raw_text, data.get("catalysts"))
        return MacroRegimeSnapshot(
            cpi_yoy_pct=round(cpi, 2),
            fed_funds_rate_pct=round(fed, 2),
            us10y_yield_pct=round(us10y, 2),
            vix_index=round(vix, 2),
            dxy_index=round(dxy, 2),
            macro_regime=regime,
            position_size_multiplier=round(mult, 2),
            summary=summary,
            catalysts=catalysts,
        )

    def parse_catalysts(
        self,
        raw_text: str = "",
        catalyst_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[CatalystEvent]:
        """Extract CatalystEvent list from structured dicts or markdown/news lines."""
        events: List[CatalystEvent] = []
        if catalyst_items:
            for item in catalyst_items:
                date_str = str(item.get("date", "TBD"))
                ev_type = str(item.get("event_type", "EARNINGS")).upper()
                desc = str(item.get("description", "Scheduled catalyst"))
                source = str(item.get("source", "Company IR / SEC EDGAR"))
                certainty, clarity = self._score_date_certainty(date_str)
                events.append(
                    CatalystEvent(
                        date=date_str,
                        event_type=ev_type,
                        description=desc,
                        certainty=item.get("certainty", certainty),
                        source=source,
                        clarity_score=float(item.get("clarity_score", clarity)),
                    )
                )

        for line in raw_text.splitlines():
            clean = line.strip()
            if not clean:
                continue
            exact_match = self._DATE_RE.search(clean)
            q_match = self._QUARTER_RE.search(clean)
            if not exact_match and not q_match:
                continue

            date_val = exact_match.group(1) if exact_match else q_match.group(1).upper()
            ev_type = self._classify_event_type(clean)
            certainty, clarity = self._score_date_certainty(date_val)
            events.append(
                CatalystEvent(
                    date=date_val,
                    event_type=ev_type,
                    description=clean.lstrip("-* "),
                    certainty=certainty,
                    source="Parsed Catalyst Feed",
                    clarity_score=clarity,
                )
            )

        return events

    @staticmethod
    def _classify_event_type(text: str) -> str:
        low = text.lower()
        if any(k in low for k in ("fda", "pdufa", "bla", "nda", "nrc", "approval", "監管")):
            return "FDA_PDUFA"
        if any(k in low for k in ("contract", "dod", "award", "doge", "合約", "標案")):
            return "GOV_CONTRACT"
        if any(k in low for k in ("fomc", "cpi", "fed", "nonfarm")):
            return "MACRO_FOMC"
        if any(k in low for k in ("launch", "product", "gtc", "conference", "產品")):
            return "PRODUCT"
        return "EARNINGS"

    def _score_date_certainty(self, date_str: str) -> tuple[str, float]:
        if self._DATE_RE.search(date_str):
            return ("HIGH", 10.0)
        if self._QUARTER_RE.search(date_str):
            return ("MEDIUM", 7.0)
        if date_str and date_str.upper() not in ("TBD", "NONE", "UNKNOWN"):
            return ("LOW", 3.0)
        return ("LOW", 0.0)

    @staticmethod
    def _extract_float(text: str, pattern: str, default: float) -> float:
        if not text:
            return default
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return default
        return default
