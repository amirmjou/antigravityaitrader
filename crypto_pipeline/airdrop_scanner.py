"""MetaMask EVM Airdrop & On-Chain Activity Scanner.

Provides read-only (public-address-only) tools to:
1. Scan a MetaMask `0x...` address across major EVM networks (Ethereum, Arbitrum,
   Optimism, Base, Linea, Scroll, ZKsync Era, and Sepolia Testnet) for balances,
   transaction counts (nonces), and anti-Sybil readiness.
2. Query the DefiLlama API for high-TVL tokenless EVM protocols that may
   distribute retroactive airdrops or run points campaigns.
3. Generate actionable terminal tables and Markdown reports.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

EVM_ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")

DEFAULT_EVM_NETWORKS: Dict[str, Dict[str, Any]] = {
    "ethereum": {
        "name": "Ethereum Mainnet",
        "rpc_urls": [
            "https://ethereum-rpc.publicnode.com",
            "https://eth.llamarpc.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "arbitrum": {
        "name": "Arbitrum One",
        "rpc_urls": [
            "https://arb1.arbitrum.io/rpc",
            "https://arbitrum-one-rpc.publicnode.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "base": {
        "name": "Base",
        "rpc_urls": [
            "https://mainnet.base.org",
            "https://base-rpc.publicnode.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "optimism": {
        "name": "Optimism",
        "rpc_urls": [
            "https://mainnet.optimism.io",
            "https://optimism-rpc.publicnode.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "linea": {
        "name": "Linea",
        "rpc_urls": [
            "https://rpc.linea.build",
            "https://linea-rpc.publicnode.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "scroll": {
        "name": "Scroll",
        "rpc_urls": [
            "https://rpc.scroll.io",
            "https://scroll-rpc.publicnode.com",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "zksync": {
        "name": "ZKsync Era",
        "rpc_urls": [
            "https://mainnet.era.zksync.io",
        ],
        "symbol": "ETH",
        "is_testnet": False,
    },
    "sepolia": {
        "name": "Sepolia Testnet",
        "rpc_urls": [
            "https://ethereum-sepolia-rpc.publicnode.com",
        ],
        "symbol": "SEP-ETH",
        "is_testnet": True,
    },
}

EVM_DEFILLAMA_CHAINS = {
    "Ethereum",
    "Arbitrum",
    "Base",
    "Optimism",
    "Linea",
    "Scroll",
    "ZKsync Era",
    "zkSync Era",
    "Polygon",
    "BSC",
    "Avalanche",
    "Blast",
    "Mantle",
    "Mode",
    "Sonic",
    "Berachain",
    "Monad",
    "Taiko",
    "Zora",
    "Starknet",
}

EXCLUDED_CATEGORIES = {
    "CEX",
    "Chain",
    "Bridge",
    "Canonical Bridge",
    "RWA",
}

EXCLUDED_NAME_SUBSTRINGS = (
    "binance",
    "coinbase",
    "bitfinex",
    "okx",
    "bybit",
    "kraken",
    "robinhood",
    "wrapped",
    "tether",
    "circle",
)


@dataclass(frozen=True)
class ChainActivity:
    """Activity snapshot for a wallet on a single EVM network."""

    network_key: str
    network_name: str
    symbol: str
    balance_native: float
    tx_count: int
    is_testnet: bool = False
    error: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.tx_count > 0 or self.balance_native > 0.0


@dataclass(frozen=True)
class WalletAirdropReport:
    """Aggregated multi-chain wallet activity and anti-Sybil readiness report."""

    address: str
    scanned_at: str
    chains: List[ChainActivity]
    active_mainnet_chains: int
    total_mainnet_txs: int
    total_mainnet_eth: float
    readiness_score: int
    readiness_tier: str
    recommendations: List[str]
    checker_links: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenlessProtocol:
    """A high-TVL tokenless DeFi protocol on EVM chains from DefiLlama."""

    name: str
    category: str
    tvl_usd: float
    change_7d_pct: Optional[float]
    evm_chains: List[str]
    url: str
    slug: str


def validate_evm_address(address: str) -> str:
    """Validate that an address is a standard 42-character hexadecimal 0x address."""
    cleaned = address.strip()
    if not EVM_ADDRESS_REGEX.match(cleaned):
        raise ValueError(
            f"Invalid EVM address '{address}'. Expected a 42-character 0x... public address."
        )
    return cleaned


class EVMAirdropScanner:
    """Scans MetaMask EVM addresses and discovers tokenless DeFi protocols."""

    DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"

    def __init__(
        self,
        networks: Optional[Dict[str, Dict[str, Any]]] = None,
        timeout: float = 8.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.networks = networks or DEFAULT_EVM_NETWORKS
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Antigravity-AirdropScanner/1.0",
                "Accept": "application/json",
            }
        )

    def _rpc_call(self, rpc_url: str, method: str, params: Sequence[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": list(params),
        }
        resp = self.session.post(rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data and data["error"]:
            raise RuntimeError(str(data["error"]))
        return data.get("result")

    def scan_chain(self, address: str, network_key: str, net_cfg: Dict[str, Any]) -> ChainActivity:
        """Query balance and nonce on a single EVM network with RPC fallback."""
        rpc_urls: List[str] = net_cfg.get("rpc_urls", [])
        last_err: Optional[str] = None

        for rpc_url in rpc_urls:
            try:
                raw_bal = self._rpc_call(rpc_url, "eth_getBalance", [address, "latest"])
                raw_nonce = self._rpc_call(rpc_url, "eth_getTransactionCount", [address, "latest"])
                wei = int(raw_bal, 16) if isinstance(raw_bal, str) else 0
                nonce = int(raw_nonce, 16) if isinstance(raw_nonce, str) else 0
                return ChainActivity(
                    network_key=network_key,
                    network_name=net_cfg["name"],
                    symbol=net_cfg.get("symbol", "ETH"),
                    balance_native=wei / 1e18,
                    tx_count=nonce,
                    is_testnet=bool(net_cfg.get("is_testnet", False)),
                    error=None,
                )
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)

        return ChainActivity(
            network_key=network_key,
            network_name=net_cfg["name"],
            symbol=net_cfg.get("symbol", "ETH"),
            balance_native=0.0,
            tx_count=0,
            is_testnet=bool(net_cfg.get("is_testnet", False)),
            error=last_err or "No RPC URLs configured",
        )

    def scan_wallet(self, address: str) -> WalletAirdropReport:
        """Scan an EVM address across all configured networks and compute readiness."""
        valid_addr = validate_evm_address(address)
        chain_results: List[ChainActivity] = []

        for key, cfg in self.networks.items():
            chain_results.append(self.scan_chain(valid_addr, key, cfg))

        mainnet_chains = [c for c in chain_results if not c.is_testnet]
        active_mainnet = sum(1 for c in mainnet_chains if c.is_active)
        total_txs = sum(c.tx_count for c in mainnet_chains)
        total_eth = sum(c.balance_native for c in mainnet_chains)

        score, tier = self._compute_readiness_score(
            active_mainnet_chains=active_mainnet,
            total_mainnet_txs=total_txs,
            total_mainnet_eth=total_eth,
        )
        recommendations = self._build_recommendations(
            chain_results=chain_results,
            active_mainnet_chains=active_mainnet,
            total_mainnet_txs=total_txs,
            total_mainnet_eth=total_eth,
        )

        checker_links = {
            "Drops.bot (Unclaimed Airdrops)": f"https://drops.bot/?address={valid_addr}",
            "DeBank (Multi-Chain Portfolio)": f"https://debank.com/profile/{valid_addr}",
            "Blockscan (All EVM Explorers)": f"https://blockscan.com/address/{valid_addr}",
            "Revoke.cash (Approval Security)": f"https://revoke.cash/address/{valid_addr}",
        }

        return WalletAirdropReport(
            address=valid_addr,
            scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            chains=chain_results,
            active_mainnet_chains=active_mainnet,
            total_mainnet_txs=total_txs,
            total_mainnet_eth=round(total_eth, 6),
            readiness_score=score,
            readiness_tier=tier,
            recommendations=recommendations,
            checker_links=checker_links,
        )

    @staticmethod
    def _compute_readiness_score(
        active_mainnet_chains: int,
        total_mainnet_txs: int,
        total_mainnet_eth: float,
    ) -> tuple[int, str]:
        """Compute a 0-100 anti-Sybil & airdrop eligibility score."""
        # 1. Chain diversity (up to 35 pts, 7 pts per active mainnet chain up to 5)
        chain_pts = min(active_mainnet_chains * 7, 35)

        # 2. Transaction volume / history (up to 40 pts)
        if total_mainnet_txs >= 100:
            tx_pts = 40
        elif total_mainnet_txs >= 50:
            tx_pts = 32
        elif total_mainnet_txs >= 20:
            tx_pts = 24
        elif total_mainnet_txs >= 5:
            tx_pts = 15
        elif total_mainnet_txs >= 1:
            tx_pts = 8
        else:
            tx_pts = 0

        # 3. Native ETH balance / anti-dust threshold (up to 25 pts)
        if total_mainnet_eth >= 0.1:
            bal_pts = 25
        elif total_mainnet_eth >= 0.02:
            bal_pts = 20
        elif total_mainnet_eth >= 0.005:
            bal_pts = 12
        elif total_mainnet_eth > 0:
            bal_pts = 5
        else:
            bal_pts = 0

        total = chain_pts + tx_pts + bal_pts
        if total >= 75:
            tier = "HIGH (Strong Retroactive Eligibility Profile)"
        elif total >= 45:
            tier = "MEDIUM (Active Wallet — Expand L2 & Protocol Depth)"
        else:
            tier = "LOW / NEW WALLET (High Sybil-Filter Risk — Needs Organic Activity)"
        return total, tier

    @staticmethod
    def _build_recommendations(
        chain_results: Sequence[ChainActivity],
        active_mainnet_chains: int,
        total_mainnet_txs: int,
        total_mainnet_eth: float,
    ) -> List[str]:
        recs: List[str] = []
        if total_mainnet_eth < 0.005:
            recs.append(
                "Maintain at least 0.005–0.01 ETH across active EVM chains; many airdrop snapshots filter out near-zero dust balances."
            )
        if active_mainnet_chains < 3:
            inactive_l2s = [
                c.network_name
                for c in chain_results
                if not c.is_testnet and not c.is_active and c.network_key in {"base", "arbitrum", "linea", "scroll"}
            ]
            if inactive_l2s:
                recs.append(
                    f"Bridge and execute organic swaps/liquidity actions on inactive L2s: {', '.join(inactive_l2s)}."
                )
        if total_mainnet_txs < 20:
            recs.append(
                f"Current mainnet nonce sum is {total_mainnet_txs}. Aim for 20+ organic transactions spread over multiple weeks/months."
            )

        sepolia = next((c for c in chain_results if c.network_key == "sepolia"), None)
        if sepolia and sepolia.balance_native == 0.0:
            recs.append(
                "Sepolia testnet balance is 0 SEP-ETH. Claim free Sepolia ETH from Google Cloud Web3 Faucet or Alchemy Faucet to participate in testnet airdrops."
            )

        if not recs:
            recs.append(
                "Strong multi-chain profile! Focus on high-TVL tokenless protocols (see DefiLlama table) and points/liquidity programs."
            )
        return recs

    def fetch_tokenless_protocols(
        self,
        min_tvl_usd: float = 15_000_000.0,
        limit: int = 15,
    ) -> List[TokenlessProtocol]:
        """Fetch top tokenless EVM DeFi protocols from DefiLlama."""
        resp = self.session.get(self.DEFILLAMA_PROTOCOLS_URL, timeout=self.timeout)
        resp.raise_for_status()
        raw_protocols = resp.json()

        candidates: List[TokenlessProtocol] = []
        for p in raw_protocols:
            symbol = p.get("symbol")
            gecko_id = p.get("gecko_id")
            if symbol not in (None, "", "-") or gecko_id:
                continue

            category = str(p.get("category") or "DeFi")
            if category in EXCLUDED_CATEGORIES:
                continue

            name_str = str(p.get("name", "Unknown"))
            if any(sub in name_str.lower() for sub in EXCLUDED_NAME_SUBSTRINGS):
                continue

            tvl = float(p.get("tvl") or 0.0)
            if tvl < min_tvl_usd:
                continue

            chains = p.get("chains") or []
            evm_chains = [c for c in chains if c in EVM_DEFILLAMA_CHAINS]
            if not evm_chains:
                continue

            change_7d = p.get("change_7d")
            candidates.append(
                TokenlessProtocol(
                    name=str(p.get("name", "Unknown")),
                    category=category,
                    tvl_usd=tvl,
                    change_7d_pct=float(change_7d) if change_7d is not None else None,
                    evm_chains=evm_chains[:5],
                    url=str(p.get("url") or f"https://defillama.com/protocol/{p.get('slug', '')}"),
                    slug=str(p.get("slug") or ""),
                )
            )

        candidates.sort(key=lambda item: item.tvl_usd, reverse=True)
        return candidates[:limit]


def format_markdown_report(
    wallet_report: Optional[WalletAirdropReport],
    protocols: Sequence[TokenlessProtocol],
) -> str:
    """Render the wallet scan and tokenless protocol list as Markdown."""
    lines: List[str] = [
        "# MetaMask Airdrop & Tokenless Protocol Report",
        "",
        f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    if wallet_report:
        lines.extend(
            [
                "## 1. Wallet Multi-Chain Activity Summary",
                "",
                f"- **Address**: `{wallet_report.address}`",
                f"- **Readiness Score**: **{wallet_report.readiness_score}/100** — `{wallet_report.readiness_tier}`",
                f"- **Active Mainnet Chains**: {wallet_report.active_mainnet_chains}",
                f"- **Total Mainnet Outgoing Txs**: {wallet_report.total_mainnet_txs}",
                f"- **Total Native ETH**: {wallet_report.total_mainnet_eth:.6f} ETH",
                "",
                "| Network | Native Balance | Outgoing Txs (Nonce) | Status |",
                "| :--- | ---: | ---: | :--- |",
            ]
        )
        for c in wallet_report.chains:
            status = (
                f"⚠️ RPC Error ({c.error[:30]})"
                if c.error
                else ("✅ Active" if c.is_active else "⬜ Inactive")
            )
            lines.append(
                f"| {c.network_name} | {c.balance_native:.5f} {c.symbol} | {c.tx_count} | {status} |"
            )

        lines.extend(["", "### Direct Paste-to-Check Links (No Wallet Signature Needed)"])
        for label, link in wallet_report.checker_links.items():
            lines.append(f"- **{label}**: {link}")

        lines.extend(["", "### Actionable Farming Recommendations"])
        for rec in wallet_report.recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    lines.extend(
        [
            "## 2. Top Tokenless EVM Protocols (DefiLlama Live Data)",
            "",
            "| Protocol | Category | TVL (USD) | 7d Change | EVM Chains | Official Link |",
            "| :--- | :--- | ---: | ---: | :--- | :--- |",
        ]
    )
    for proto in protocols:
        chg = f"{proto.change_7d_pct:+.1f}%" if proto.change_7d_pct is not None else "N/A"
        chains_str = ", ".join(proto.evm_chains)
        lines.append(
            f"| **{proto.name}** | {proto.category} | ${proto.tvl_usd:,.0f} | {chg} | {chains_str} | {proto.url} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_console_output(
    wallet_report: Optional[WalletAirdropReport],
    protocols: Sequence[TokenlessProtocol],
    console: Optional[Console] = None,
) -> None:
    """Display rich tables in the terminal."""
    out = console or Console()

    if wallet_report:
        out.print(
            Panel.fit(
                f"[bold cyan]Address:[/bold cyan] {wallet_report.address}\n"
                f"[bold green]Readiness Score:[/bold green] {wallet_report.readiness_score}/100 ({wallet_report.readiness_tier})\n"
                f"[bold yellow]Active Mainnet Chains:[/bold yellow] {wallet_report.active_mainnet_chains} | "
                f"[bold yellow]Total Txs:[/bold yellow] {wallet_report.total_mainnet_txs} | "
                f"[bold yellow]Total ETH:[/bold yellow] {wallet_report.total_mainnet_eth:.5f} ETH",
                title="MetaMask Wallet Airdrop Readiness",
            )
        )

        chain_table = Table(title="Multi-Chain EVM Activity")
        chain_table.add_column("Network", style="cyan")
        chain_table.add_column("Balance", justify="right", style="green")
        chain_table.add_column("Tx Count (Nonce)", justify="right", style="magenta")
        chain_table.add_column("Status", style="white")

        for c in wallet_report.chains:
            status = "RPC Error" if c.error else ("Active" if c.is_active else "Inactive")
            chain_table.add_row(
                c.network_name,
                f"{c.balance_native:.5f} {c.symbol}",
                str(c.tx_count),
                status,
            )
        out.print(chain_table)

        out.print("\n[bold underline]Actionable Recommendations:[/bold underline]")
        for rec in wallet_report.recommendations:
            out.print(f" • {rec}")

        out.print("\n[bold underline]Safe Paste-to-Check Portals:[/bold underline]")
        for label, url in wallet_report.checker_links.items():
            out.print(f" • {label}: {url}")
        out.print()

    proto_table = Table(title="Top Tokenless EVM Protocols on DefiLlama (Potential Airdrops)")
    proto_table.add_column("Protocol", style="bold cyan")
    proto_table.add_column("Category", style="yellow")
    proto_table.add_column("TVL (USD)", justify="right", style="green")
    proto_table.add_column("7d %", justify="right")
    proto_table.add_column("EVM Chains", style="white")
    proto_table.add_column("URL", style="dim")

    for p in protocols:
        chg = f"{p.change_7d_pct:+.1f}%" if p.change_7d_pct is not None else "N/A"
        proto_table.add_row(
            p.name,
            p.category,
            f"${p.tvl_usd:,.0f}",
            chg,
            ", ".join(p.evm_chains[:4]),
            p.url,
        )
    out.print(proto_table)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a MetaMask 0x address for EVM activity and list top tokenless DeFi protocols."
    )
    parser.add_argument(
        "--address",
        "-a",
        type=str,
        default=None,
        help="Public MetaMask EVM address (0x...) to scan across chains.",
    )
    parser.add_argument(
        "--min-tvl",
        type=float,
        default=15_000_000.0,
        help="Minimum TVL in USD for filtering tokenless DefiLlama protocols (default: 15,000,000).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top tokenless EVM protocols to display (default: 15).",
    )
    parser.add_argument(
        "--export",
        "-o",
        type=str,
        default=None,
        help="Optional path to export a Markdown report (e.g. sessions/airdrop_report.md).",
    )
    args = parser.parse_args(argv)

    scanner = EVMAirdropScanner()
    wallet_report: Optional[WalletAirdropReport] = None
    if args.address:
        wallet_report = scanner.scan_wallet(args.address)

    protocols = scanner.fetch_tokenless_protocols(
        min_tvl_usd=args.min_tvl,
        limit=args.top,
    )

    render_console_output(wallet_report, protocols)

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        md = format_markdown_report(wallet_report, protocols)
        export_path.write_text(md, encoding="utf-8")
        print(f"\nSaved Markdown report to: {export_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
