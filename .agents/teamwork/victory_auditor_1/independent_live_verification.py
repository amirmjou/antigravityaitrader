"""Independent Live Terminal & MetaMask Bridge Auditor Verification Script.

Inspects the live running process on port 8899 directly over the network:
- Health endpoint
- Authentication gate (200 with token, 401 without / invalid)
- WebSocket telemetry streaming (/ws/telemetry) with schema inspection
- Server-Sent Events reasoning stream (/events/reasoning) with schema inspection
- MetaMask bridge account sync (/wallet_syncAccount and /rpc)
- Transaction staging & confirmation lifecycle (/send-transaction & /confirm-transaction)
"""
import asyncio
import json
import urllib.error
import urllib.request
import websockets

BASE_URL = "http://127.0.0.1:8899"
WS_URL = "ws://127.0.0.1:8899/ws/telemetry"
TOKEN = "ag_live_metamask_2026_token"

results = {}

def http_get(path, headers=None, token_param=None):
    url = f"{BASE_URL}{path}"
    if token_param:
        delim = "&" if "?" in url else "?"
        url = f"{url}{delim}token={token_param}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)

def http_post(path, data, headers=None, token_param=None):
    url = f"{BASE_URL}{path}"
    if token_param:
        delim = "&" if "?" in url else "?"
        url = f"{url}{delim}token={token_param}"
    post_data = json.dumps(data).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=post_data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)

def test_health():
    code, body, _ = http_get("/health")
    data = json.loads(body)
    assert code == 200, f"Expected 200, got {code}"
    assert data.get("status") == "ok", f"Expected ok, got {data}"
    results["health"] = {"code": code, "data": data}
    print("PASS: /health returned 200 ok")

def test_auth():
    code_no_token, _, _ = http_get("/")
    assert code_no_token == 401, f"Expected 401 without token, got {code_no_token}"

    code_bad_token, _, _ = http_get("/", token_param="bad_invalid_token")
    assert code_bad_token == 401, f"Expected 401 with bad token, got {code_bad_token}"

    code_valid, body_valid, _ = http_get("/", token_param=TOKEN)
    assert code_valid == 200, f"Expected 200 with valid token, got {code_valid}"
    assert "Antigravity" in body_valid or "candleChart" in body_valid, "UI HTML content check failed"

    code_bearer, body_bearer, _ = http_get("/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert code_bearer == 200, f"Expected 200 with Bearer token, got {code_bearer}"

    results["auth"] = {
        "no_token_status": code_no_token,
        "bad_token_status": code_bad_token,
        "valid_token_status": code_valid,
        "bearer_token_status": code_bearer,
    }
    print("PASS: Auth gate enforcement (401 without token, 200 with token/bearer)")

async def test_websocket():
    ws_uri = f"{WS_URL}?token={TOKEN}"
    async with websockets.connect(ws_uri) as ws:
        await ws.send(json.dumps({"type": "subscribe", "channels": ["candles", "indicators", "orderbook", "trades"]}))
        messages = []
        for _ in range(6):
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            messages.append(data)
            m_type = data.get("message_type")
            payload = data.get("payload", {})
            print(f"  [WS Telemetry Frame] message_type={m_type} keys={list(payload.keys())}")
            if m_type == "indicator_update":
                print(f"    -> Indicators: symbol={payload.get('symbol')} RSI={payload.get('rsi_14')} MACD={payload.get('macd')} ADX={payload.get('adx_14')} EMA20={payload.get('ema_20')}")
            elif m_type == "ticker_update":
                print(f"    -> Ticker Candle: close={payload.get('close')} vol={payload.get('volume')}")
            elif m_type == "orderbook_snapshot":
                print(f"    -> OrderBook: symbol={payload.get('symbol')} bids_count={len(payload.get('bids', []))} asks_count={len(payload.get('asks', []))}")
        
        types = set(m.get("message_type") for m in messages)
        assert len(messages) >= 3, f"Expected at least 3 messages, got {len(messages)}"
        assert "ticker_update" in types or "indicator_update" in types or "orderbook_snapshot" in types
        results["websocket"] = {
            "received_count": len(messages),
            "message_types": list(types),
        }
        print(f"PASS: WebSocket telemetry stream active and validated: types={list(types)}")

async def test_sse_reasoning():
    url = f"{BASE_URL}/events/reasoning?token={TOKEN}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=12)
    events = []
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < 12 and len(events) < 3:
        line = resp.readline().decode("utf-8")
        if not line:
            break
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    data = json.loads(payload)
                    events.append(data)
                    print(f"  [SSE Reasoning Event] role={data.get('agent_role')} event={data.get('event')} token={data.get('token')[:60]}...")
                except Exception:
                    pass
    assert len(events) >= 1, f"Expected at least 1 SSE reasoning event, got {len(events)}"
    results["sse_reasoning"] = {
        "event_count": len(events),
        "roles": [e.get("agent_role") for e in events],
        "events": [e.get("event") for e in events],
    }
    print(f"PASS: SSE reasoning stream active ({len(events)} events collected, roles={results['sse_reasoning']['roles']})")

def test_bridge_sync_and_tx():
    test_address = "0x71C8363837031a3609400472A3a52902230460A3"
    
    # 1. /wallet_syncAccount
    code, body, _ = http_post("/wallet_syncAccount", {"address": test_address, "chain_id": 42161}, token_param=TOKEN)
    assert code == 200, f"Expected 200, got {code}: {body}"
    sync_data = json.loads(body)
    assert sync_data.get("status") == "synchronized"
    assert test_address in sync_data.get("connected_accounts", [])
    print(f"PASS: /wallet_syncAccount synced {test_address} on chain {sync_data.get('chain_id')}")

    # 2. /rpc with eth_accounts
    code, body, _ = http_post("/rpc", {"jsonrpc": "2.0", "id": 101, "method": "eth_accounts", "params": []}, token_param=TOKEN)
    assert code == 200
    rpc_accounts = json.loads(body)
    assert test_address in rpc_accounts.get("result", [])
    print(f"PASS: /rpc eth_accounts returned synced address")

    # 3. /send-transaction (stage)
    tx_payload = {
        "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "amount_in_wei": 200000000,
        "amount_out_min_wei": 226000,
        "chain_id": 42161,
        "trade_value_usd": 40.0,
    }
    code, body, _ = http_post("/send-transaction", tx_payload, token_param=TOKEN)
    assert code == 200, f"Expected 200, got {code}: {body}"
    staged = json.loads(body)
    assert staged.get("status") == "staged"
    req_id = staged.get("request_id")
    assert req_id, "Missing request_id"
    print(f"PASS: /send-transaction staged request_id={req_id}")

    # 4. /confirm-transaction (confirm)
    synth_hash = "0x" + "b" * 64
    confirm_payload = {
        "request_id": req_id,
        "tx_hash": synth_hash,
        "success": True,
    }
    code, body, _ = http_post("/confirm-transaction", confirm_payload, token_param=TOKEN)
    assert code == 200, f"Expected 200, got {code}: {body}"
    confirmed = json.loads(body)
    assert confirmed.get("status") == "confirmed"
    assert confirmed.get("tx_hash") == synth_hash
    print(f"PASS: /confirm-transaction confirmed tx_hash={synth_hash}")

    # 5. /confirm-transaction rejection handling
    code, body, _ = http_post("/send-transaction", tx_payload, token_param=TOKEN)
    req_id2 = json.loads(body)["request_id"]
    reject_payload = {
        "request_id": req_id2,
        "success": False,
        "error_reason": "User rejected transaction in MetaMask (error 4001)",
    }
    code, body, _ = http_post("/confirm-transaction", reject_payload, token_param=TOKEN)
    assert code == 200, f"Expected 200, got {code}: {body}"
    rejected = json.loads(body)
    assert rejected.get("status") == "rejected"
    print(f"PASS: /confirm-transaction handled user cancellation/rejection")

    results["bridge"] = {
        "synced_address": test_address,
        "staged_request_id": req_id,
        "confirmed_hash": synth_hash,
        "rejected_request_id": req_id2,
    }

async def main():
    print("=== STARTING INDEPENDENT LIVE NETWORK AUDIT OF PORT 8899 ===")
    test_health()
    test_auth()
    await test_websocket()
    await test_sse_reasoning()
    test_bridge_sync_and_tx()
    print("=== ALL LIVE NETWORK AUDIT CHECKS PASSED ===")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
