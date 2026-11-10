# Explorer 2 Handoff Report: Secret, Credential & Keystore Protection Survey

## 1. Observation

A systematic survey was conducted across the codebase to identify how wallet private keys, keystores, third-party API keys, and external RPC credentials are loaded, stored, processed, and broadcast. Below are the verbatim code citations and architectural observations.

---

### 1.1 Wallet Private Keys & Keystore Handling (`execution/wallet/`)

#### 1.1.1 Exposure of Plaintext Private Key via Public Property
In `execution/wallet/hot_signer.py` (lines 40–45):
```python
    @property
    def private_key_hex(self) -> str:
        """Returns the 0x-prefixed private key in hex."""
        h = self._account.key.hex()
        return h if h.startswith("0x") else "0x" + h
```
- **Direct observation**: `HotKeystoreSigner` exposes a public getter `private_key_hex` that serializes the unencrypted private key into a standard Python string. Any internal component, serialization routine, logging framework (e.g. `vars(signer)`), or inspection utility accessing this property obtains the raw unencrypted private key.

#### 1.1.2 Keystore Loading, Decryption & In-Memory Lifetime
In `execution/wallet/hot_signer.py` (lines 24–34, 69–85, 87–104):
```python
    def __init__(
        self,
        account: LocalAccount,
        web3_provider: Optional[Any] = None,
        default_chain_id: int = 42161,
    ):
        self._account: LocalAccount = account
        self.w3 = web3_provider
        self.default_chain_id = default_chain_id
        self._nonce: Optional[int] = None
...
    @classmethod
    def from_keystore_json(
        cls,
        keystore_data: Union[str, Dict[str, Any]],
        password: str,
        web3_provider: Optional[Any] = None,
        default_chain_id: int = 42161,
    ) -> HotKeystoreSigner:
        """Decrypt an encrypted Ethereum JSON keystore (V3)."""
        if isinstance(keystore_data, str):
            keystore_dict = json.loads(keystore_data)
        else:
            keystore_dict = keystore_data

        private_key = Account.decrypt(keystore_dict, password)
        account = Account.from_key(private_key)
        return cls(account=account, web3_provider=web3_provider, default_chain_id=default_chain_id)
```
- **Direct observation**: The keystore is decrypted in-memory using `Account.decrypt`. The resulting `LocalAccount` object holds `account.key` as immutable `bytes` in standard heap memory for the entire lifetime of the `HotKeystoreSigner` instance. There is no memory locking (`mlock`), zeroing mechanism (secure wipe/`memset`), or memory isolation.

#### 1.1.3 Insecure Keystore File Creation Permissions
In `execution/wallet/hot_signer.py` (lines 109–122):
```python
    def save_keystore_file(
        self,
        file_path: Union[str, Path],
        password: str,
        kdf: str = "scrypt",
    ) -> Path:
        """Save encrypted keystore to target file path."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        keystore_dict = self.export_keystore(password, kdf=kdf)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(keystore_dict, f, indent=2)
        return path
```
- **Direct observation**: `save_keystore_file` writes the encrypted keystore using default `open(..., "w")` without setting POSIX file permissions (such as `0600` via `os.open` with `O_CREAT | O_EXCL` and `os.chmod`). On shared cloud hosts or containers where `umask` is `0022`, the resulting keystore JSON file is world-readable (`-rw-r--r--`).

#### 1.1.4 Unprotected Fallback in Transaction Execution
In `execution/wallet/router.py` (lines 91–105, 138–144):
```python
        if signer_mode == "hot_keystore" and self.hot_signer is not None:
            try:
                tx_dict = {
                    "to": self.config.router_address,
                    "value": 0,
                    "chainId": self.config.chain_id,
                    "data": "0x",
                    "gas": 145000,
                }
                signed_data = self.hot_signer.sign_transaction(tx_dict)
                raw_tx = signed_data["raw_transaction"]
            except Exception:
                raw_tx = f"0xRAW_SIGNED_TX_CHAIN_{self.config.chain_id}_{signer_mode}_{request.amount_in_wei}"
        else:
            raw_tx = f"0xRAW_SIGNED_TX_CHAIN_{self.config.chain_id}_{signer_mode}_{request.amount_in_wei}"
```
And in exception handling:
```python
        except Exception as e:
            err_msg = str(e)
            return SwapExecutionResult(
                success=False,
                revert_reason=err_msg,
                signer_mode=signer_mode,  # type: ignore
            )
```
- **Direct observation**: Any uncaught exception thrown during transaction signing or node dispatch is stringified into `err_msg` and returned in `SwapExecutionResult.revert_reason`. If Web3 or RPC errors contain host/URL parameters, they are returned in the result model.

---

### 1.2 Third-Party API Key Management & Environment Variables

#### 1.2.1 LLM Provider API Keys
In `core/llm_clients/api_key_env.py` (lines 14–46):
```python
PROVIDER_API_KEY_ENV: dict[str, str | None] = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "azure":      "AZURE_OPENAI_API_KEY",
    "bedrock":    None,
    "xai":        "XAI_API_KEY",
    "deepseek":   "DEEPSEEK_API_KEY",
    "qwen":       "DASHSCOPE_API_KEY",
    "qwen-cn":    "DASHSCOPE_CN_API_KEY",
    "glm":        "ZHIPU_API_KEY",
    "glm-cn":     "ZHIPU_CN_API_KEY",
    "minimax":    "MINIMAX_API_KEY",
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral":    "MISTRAL_API_KEY",
    "kimi":       "MOONSHOT_API_KEY",
    "groq":       "GROQ_API_KEY",
    "nvidia":     "NVIDIA_API_KEY",
    "chatgpt":    None,
    "ollama":     None,
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}
```
In `core/llm_clients/antigravity_client.py` (lines 75–81):
```python
        api_key = (
            self.kwargs.get("api_key")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
```
- **Direct observation**: All LLM credentials rely on ambient process environment variables (`os.environ`).

#### 1.2.2 Plaintext Storage via python-dotenv
In `core/cli/prompts.py` (lines 737–746):
```python
    env_path = find_dotenv(usecwd=True) or str(Path.cwd() / ".env")
    if not os.path.exists(env_path):
        os.close(os.open(env_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    os.chmod(env_path, 0o600)
    set_key(env_path, env_var, key)
    os.environ[env_var] = key
    console.print(f"[green]Saved {env_var} to {env_path}[/green]")
    return key
```
- **Direct observation**: `ensure_api_key` writes plaintext API keys directly into `.env` at `Path.cwd() / ".env"` using `python-dotenv.set_key`. While `os.chmod(env_path, 0o600)` is invoked, on Windows systems POSIX file permission bits are ignored, leaving `.env` subject to inherited Windows NTFS permissions.

#### 1.2.3 Data Vendors (Alpha Vantage, FRED, TypeSafe)
- `core/dataflows/vendors/alpha_vantage/common.py` (lines 28–35):
  `os.getenv("ALPHA_VANTAGE_API_KEY")`
- `core/dataflows/vendors/fred.py` (lines 102–110):
  `os.getenv("FRED_API_KEY")`
- `core/agents/post_screen.py` (lines 80, 139):
  `os.environ.get("TYPESAFE_API_KEY")`

#### 1.2.4 Web3 RPC Node URLs
In `tests/e2e/contracts.py` (line 135) and `tests/e2e/conftest.py` (lines 59, 74):
```python
class ChainExecutionConfig(BaseModel):
    chain_id: int
    chain_name: str
    rpc_url: str
...
```
- **Direct observation**: `ChainExecutionConfig.rpc_url` is a plain string. In live cloud environments, authenticated private endpoints (such as Alchemy: `https://arb-mainnet.g.alchemy.com/v2/<API_KEY>` or Infura: `https://arbitrum-mainnet.infura.io/v3/<API_KEY>`) embed the API key directly in the URL path. No masking or redaction exists when storing, logging, or passing this config.

---

### 1.3 Telemetry, SSE Streams & Plaintext Leakage Vectors

#### 1.3.1 SSE Deliberation Stream Public Exposure
In `visualization/server/sse_router.py` (lines 47–76):
```python
@sse_router.get("/events/reasoning")
@sse_router.get("/api/deliberation/stream")
async def stream_reasoning(
    request: Request,
    since_id: Optional[int] = Query(None, description="Event sequence ID to replay from"),
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    limit: Optional[int] = Query(None, description="Optional maximum number of events to yield before closing"),
):
...
    return StreamingResponse(
        sse_event_generator(request, effective_since, hub, limit=limit),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
```
- **Direct observation**: Endpoints `/events/reasoning` and `/api/deliberation/stream` have:
  1. **Zero authentication or authorization checks**.
  2. `Access-Control-Allow-Origin: *` (wildcard CORS).
  3. Real-time broadcast and historical backlog replay of `AgentDeliberationEvent` instances from a 2,000-event memory buffer.

#### 1.3.2 Tool Call & State Snapshot Emission
In `visualization/telemetry/callbacks.py` (lines 42–62):
```python
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Emitted when an agent invokes a tool (e.g. CCXT ticker fetch)."""
        tool_name = serialized.get("name", "tool") if isinstance(serialized, dict) else str(serialized)
        self.hub.publish_event(
            event_type="tool_call",
            role=self.current_role,
            token=f"{tool_name}({input_str})",
            snapshot={"tool": tool_name, "input": input_str},
            debate_round=self.debate_round,
        )

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        """Emitted when tool returns result."""
        out_summary = output if isinstance(output, dict) else str(output)
        self.hub.publish_event(
            event_type="tool_call",
            role=self.current_role,
            token=f"Result: {str(out_summary)[:120]}",
            snapshot={"output": out_summary},
            debate_round=self.debate_round,
        )
```
And lines 106–115:
```python
    def publish_trade_execution(self, role: str, tx_info: Dict[str, Any] | Any) -> None:
        """Publish on-chain or paper trade execution telemetry."""
        snapshot = tx_info if isinstance(tx_info, dict) else (tx_info.model_dump() if hasattr(tx_info, "model_dump") else str(tx_info))
        tx_hash = snapshot.get("tx_hash", "0x0") if isinstance(snapshot, dict) else "0x0"
        self.hub.publish_event(
            event_type="trade_telemetry",
            role=role,
            token=f"Trade executed: tx_hash={tx_hash}",
            snapshot=snapshot if isinstance(snapshot, dict) else {"tx": snapshot},
        )
```
- **Direct observation**: Any input string passed to a tool (`input_str`), the tool output (`out_summary`), and trade execution metadata are packaged verbatim into `state_snapshot` and broadcast over the unauthenticated SSE stream and WebSocket. If an agent executes a tool with an RPC URL, API key, wallet address, or private strategy parameter, it is emitted to all listeners without scrubbing.

#### 1.3.3 Selective Outbound Scrubbing Disparity
In `core/dataflows/net.py` (lines 6–24):
```python
def get_scrubbed(url: str, *, params: dict, timeout: float, secret: str, passthrough=()):
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code not in passthrough:
            response.raise_for_status()
        return response
    except requests.RequestException as exc:
        error = type(exc)(str(exc).replace(secret, "***")) if secret else exc
    raise error
```
- **Direct observation**: While `get_scrubbed` redacts `secret` from `requests.RequestException` for Alpha Vantage and FRED, this protection is **absent** from:
  - `crypto_pipeline/airdrop_scanner.py` (line 229: `self.session.post(rpc_url, json=payload)`).
  - `crypto_pipeline/ingestion/feeds.py` (lines 204, 246: `requests.get(...)`).
  - Web3 HTTPProvider / RPC callers in `execution/guardrails/pipeline.py` and `execution/wallet/router.py`.
  - Child process execution in `crypto_pipeline/remote_agent/bridge.py` (`subprocess.run(["agy", ...])`).

---

### 1.4 EIP-1193 Bridge Server Exposure
In `execution/wallet/eip1193_bridge.py` (lines 191–197, 216–226, 262–312):
```python
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
```
- **Direct observation**:
  - The bridge server allows cross-origin requests from ANY domain (`allow_origins=["*"]`) with `allow_credentials=True`.
  - `/send-transaction`, `/confirm-transaction`, `/sign-typed-data`, and `/rpc` (handling `eth_sendTransaction`, `personal_sign`, and `eth_signTypedData_v4`) have **zero authentication headers, tokens, or sessions**.
  - Any web page running in a browser that makes cross-origin requests to `http://localhost:8899/send-transaction` or `http://<cloud-ip>:8899/rpc` can stage and manipulate trade executions.

---

### 1.5 Subprocess Environment Variable Inheritance
In `crypto_pipeline/remote_agent/bridge.py` (lines 131–142):
```python
        if self.prefer_cli and shutil.which("agy"):
            try:
                cmd = self.build_command(prompt, output_format="json")
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    check=False,
                )
```
- **Direct observation**: `subprocess.run` is called without an explicit `env` parameter. By default, Python passes the entire parent `os.environ` to the child process, including all cloud credentials, LLM keys, and database tokens.

---

## 2. Logic Chain

```
[Observation: HotKeystoreSigner.private_key_hex returns 0x-prefixed key]
       │
       ▼
[Step 1: Any logging, serializer, traceback, or test inspection can dump raw private key]
       │
       ▼
[Risk 1: Keystore Compromise via Accidental Logging or Diagnostic Dumps]

[Observation: HotKeystoreSigner loads decrypted key as bytes into Python heap for process lifetime]
       │
       ▼
[Step 2: Python does not support memory locking or deterministic zeroing; memory dump / core dump reveals key]
       │
       ▼
[Risk 2: Memory Extraction via Crash Dumps, Swap Files, or Container Memory Introspection]

[Observation: SSE stream /events/reasoning and WebSocket /ws/telemetry have no auth and allow CORS *]
       │
       ▼
[Step 3: Tool calls, thought tokens, trade telemetry, and internal parameters broadcast in plaintext to all listeners]
       │
       ▼
[Risk 3: Information Disclosure, Strategy Front-Running, and Credential Leakage via Open SSE/WS]

[Observation: EIP-1193 Bridge /rpc, /send-transaction have wildcard CORS and no auth]
       │
       ▼
[Step 4: Arbitrary remote or browser clients can invoke RPC methods, stage swaps, and confirm executions]
       │
       ▼
[Risk 4: Unauthorized Transaction Injection and Remote Execution Hijacking]

[Observation: ensure_api_key writes plaintext secrets to .env file in project root]
       │
       ▼
[Step 5: Secrets persist unencrypted on disk; Windows ignores 0600 chmod; Docker layers or git commits risk exposure]
       │
       ▼
[Risk 5: Persistent Credential Leakage in Cloud Storage or Version Control]

[Observation: Web3 RPC URLs with embedded API tokens not scrubbed in exception handlers]
       │
       ▼
[Step 6: Network disconnects or node rate-limiting raises exceptions printing full URL with API token]
       │
       ▼
[Risk 6: Third-Party Node API Key Leakage into Application Logs and Error Traces]
```

---

## 3. Caveats

1. **Local Test Environments vs. Production Cloud**: Current test suites rely heavily on offline mock adapters (`MockGoPlusClient`, `MockUniswapV3Quoter`, `MockWeb3Provider`). Real network failures against live Alchemy/Infura or live GoPlus endpoints were not triggered in unit tests, meaning real-world traceback formats with embedded tokens must be hardened proactively.
2. **Windows vs. Linux File Permissions**: Testing was conducted on Windows where `os.chmod(path, 0o600)` does not configure discretionary access control lists (DACLs). Production cloud deployments running on Linux will enforce POSIX mode bits, but defense-in-depth requires explicit umask configuration and non-root execution.
3. **Hardware Wallets & Cloud KMS**: The current architecture does not yet contain a pluggable Cloud KMS signer interface (e.g. AWS KMS or GCP Cloud KMS); transactions currently require either local `eth-account` hot signing or the interactive browser extension bridge.

---

## 4. Conclusion & Prioritized Vulnerability Catalog

The codebase exhibits strong architectural modularity and safety guardrails at the contract execution level (L1–L5), but presents **critical vulnerabilities in secret storage, transport security, and credential exposure** that must be resolved prior to live cloud deployment:

### Vulnerability Matrix

| ID | Component | Severity | Description | Remediated By |
|---|---|---|---|---|
| **SEC-01** | `execution/wallet/hot_signer.py` | **CRITICAL** | `private_key_hex` property exposes unencrypted private key; in-memory lifetime indefinite in heap without core dump protection | Remove getter or restrict to debug mode; implement KMS or encrypted memory vault |
| **SEC-02** | `execution/wallet/eip1193_bridge.py` | **CRITICAL** | `/send-transaction`, `/confirm-transaction`, `/rpc` exposed with `allow_origins=["*"]` and zero authentication | Restrict CORS to specific frontend domain; require HMAC/Bearer token authentication |
| **SEC-03** | `visualization/server/sse_router.py` | **HIGH** | `/events/reasoning` and `/api/deliberation/stream` stream full tool inputs, outputs, and reasoning tokens without authentication and with wildcard CORS | Require Bearer auth token on SSE/WS; sanitize tool parameters before publishing to hub |
| **SEC-04** | `core/cli/prompts.py` | **HIGH** | Plaintext API keys written to `.env` file on disk | Use cloud secret manager (AWS Secrets Manager, GCP Secret Manager, or environment injection) |
| **SEC-05** | `crypto_pipeline/remote_agent/bridge.py` | **MEDIUM** | `subprocess.run` inherits entire environment containing all API keys and secrets | Use explicit `env` whitelist containing only required variables |
| **SEC-06** | `execution/wallet/hot_signer.py` | **MEDIUM** | `save_keystore_file` creates files without explicit `0600` permissions | Use `os.open` with `O_CREAT \| O_EXCL` and mode `0600` |
| **SEC-07** | Outbound HTTP/RPC clients | **MEDIUM** | Outbound RPC and HTTP errors (Alchemy, Infura, GoPlus, CCXT) do not scrub tokens from exceptions | Extend `get_scrubbed` pattern or install requests/urllib3 redaction hook |

---

## 5. Verification Method

To independently verify these findings and confirm existing baseline stability:

### 5.1 Code Path Inspection
1. Inspect `execution/wallet/hot_signer.py` lines 40–45 to verify `private_key_hex` property.
2. Inspect `visualization/server/sse_router.py` lines 67–76 to verify lack of authentication and wildcard CORS on SSE reasoning endpoints.
3. Inspect `execution/wallet/eip1193_bridge.py` lines 191–197 to verify `allow_origins=["*"]` and unauthenticated `/rpc` and `/send-transaction`.
4. Inspect `core/cli/prompts.py` lines 737–746 to verify `.env` file writing.

### 5.2 Test Baseline Execution
Run existing unit and adversarial test suites using python:
```powershell
python -m pytest tests/unit/test_execution.py -v
python -m pytest tests/adversarial/test_m2_guardrails_adversarial.py -v
python -m pytest tests/adversarial/test_m2_adversarial_challenge.py -v
python tests/e2e/run_all.py
```

### 5.3 Concrete Invalidation / Remediation Verification
- When hardening controls are introduced, automated tests must verify:
  1. Requests to `/events/reasoning` and `/api/deliberation/stream` without a valid authentication header receive `401 Unauthorized`.
  2. Requests to `/rpc` or `/send-transaction` without authentication receive `401 Unauthorized`.
  3. Pre-flight OPTIONS requests from unapproved origins receive CORS rejection.
  4. Core dump generation is disabled (`prctl(PR_SET_DUMPABLE, 0)` on Linux).
  5. Keystore file generation creates files with strict `0600` permissions.
