---
name: airdrop-scan
description: Scan a MetaMask EVM 0x address for multi-chain airdrop readiness, unclaimed airdrop links, and live high-TVL tokenless DeFi protocols from DefiLlama.
---

# MetaMask Airdrop & On-Chain Activity Scanner

Use this skill when the user wants to check their MetaMask wallet (`0x...`) for unclaimed airdrops, assess their multi-chain anti-Sybil readiness, or discover top tokenless EVM DeFi protocols to farm.

**Usage**: `/airdrop-scan [0xADDRESS]`  
**Example**: `/airdrop-scan 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`

---

## Security Rules (Mandatory)
1. **Public Address Only**: Never ask for or accept private keys, seed phrases, or wallet signatures.
2. **Paste-to-Check First**: Always surface read-only lookup URLs (`Drops.bot`, `DeBank`, `Blockscan`, `Revoke.cash`) before recommending any on-chain claim interaction.

---

## Execution Protocol

### Step 1: Run the Workspace Scanner CLI
Execute the Python scanner in `crypto_pipeline.airdrop_scanner`:

- **With a public `0x` address**:
  ```powershell
  python -m crypto_pipeline.airdrop_scanner --address <0xADDRESS> --top 15 --export sessions/airdrop_report.md
  ```
- **Without an address (protocol discovery only)**:
  ```powershell
  python -m crypto_pipeline.airdrop_scanner --top 15 --export sessions/airdrop_report.md
  ```

### Step 2: Review Multi-Chain Readiness & Anti-Sybil Metrics
If a wallet address was provided, report:
- **Readiness Score (`0–100`) & Tier**:
  - **Chain Diversity** (up to 35 pts across Ethereum, Arbitrum, Base, Optimism, Linea, Scroll, ZKsync Era)
  - **Transaction Count / Nonce** (up to 40 pts for `>= 100` organic transactions)
  - **Anti-Dust Native Balance** (up to 25 pts for holding `>= 0.005–0.1 ETH`)
- **Direct Paste-to-Check Links**:
  - `https://drops.bot/?address=<0xADDRESS>`
  - `https://debank.com/profile/<0xADDRESS>`
  - `https://revoke.cash/address/<0xADDRESS>`

### Step 3: Present Actionable Farming Plan
1. Highlight the top tokenless EVM protocols from `sessions/airdrop_report.md` matching the user's active chains or capital level.
2. If the wallet has `0` balance on Sepolia or mainnet L2s, provide free testnet faucet links (Google Cloud Web3 Sepolia Faucet, Alchemy Sepolia Faucet) and low-gas L2 onboarding steps (Base / Arbitrum / Linea).
