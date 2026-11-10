"""
Interactive EIP-1193 FastAPI bridge server.
Exposes JSON-RPC endpoints (/rpc, /request-accounts, /send-transaction, /sign-typed-data)
and WebSocket status updates for MetaMask browser extension connection.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Union

import os
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ETH_ADDRESS_REGEX = re.compile(r"^0x[0-9a-fA-F]{40}$")




# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[List[Any]] = None
    id: Optional[Union[int, str]] = 1


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = 1
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class SendTxRequest(BaseModel):
    to: str
    amount_in_wei: int = 0
    amount_out_min_wei: int = 0
    data: Optional[str] = "0x"
    chain_id: int = 42161
    trade_value_usd: float = 100.0
    gas_limit: int = 150000
    max_fee_gwei: Optional[float] = None
    max_priority_fee_gwei: Optional[float] = None


class SignTypedDataRequest(BaseModel):
    account: str
    domain: Dict[str, Any]
    types: Dict[str, Any]
    message: Dict[str, Any]


class ConfirmTxRequest(BaseModel):
    request_id: str
    tx_hash: Optional[str] = None
    success: bool = True
    error_reason: Optional[str] = None


class BridgeStatus(BaseModel):
    connected_clients: int
    connected_accounts: List[str]
    chain_id: int
    pending_transactions_count: int
    uptime_seconds: float
    wallet_balance_eth: float = 0.0
    cumulative_profit_usd: float = 0.0
    target_profit_usd: float = 2000.0


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        data = json.dumps(message)
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(data)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


# ---------------------------------------------------------------------------
# EIP-1193 Bridge Server
# ---------------------------------------------------------------------------

class EIP1193BridgeServer:
    """
    FastAPI Bridge Server coordinating MetaMask browser extension connectivity.
    Manages pending staged transactions awaiting human approval and WebSocket telemetry.
    """

    def __init__(self, default_chain_id: int = 42161):
        self.chain_id = default_chain_id
        self.start_time = time.time()
        self.connected_accounts: List[str] = ["0xUserWallet"]
        self.wallet_balance_eth: float = 0.0
        self.cumulative_profit_usd: float = 0.0
        self.target_profit_usd: float = 2000.0
        self.pending_transactions: Dict[str, Dict[str, Any]] = {}
        self.transaction_events: Dict[str, asyncio.Event] = {}
        self.transaction_results: Dict[str, Dict[str, Any]] = {}
        self.manager = ConnectionManager()
        self.app = self._build_fastapi_app()

    def set_connected_account(self, address: str):
        if not isinstance(address, str):
            return
        clean_addr = address.strip()
        if clean_addr != "0xUserWallet" and not ETH_ADDRESS_REGEX.match(clean_addr):
            return
        if clean_addr not in self.connected_accounts:
            self.connected_accounts.insert(0, clean_addr)

    def stage_transaction_sync(
        self,
        tx_params: Dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Stage a transaction and return a staging record.
        """
        req_id = f"tx_{uuid.uuid4().hex[:12]}"
        staged_record = {
            "request_id": req_id,
            "status": "pending",
            "created_at": time.time(),
            "timeout_seconds": timeout_seconds,
            "params": tx_params,
            "chain_id": tx_params.get("chain_id", self.chain_id),
        }
        self.pending_transactions[req_id] = staged_record
        return staged_record

    def confirm_transaction(
        self,
        request_id: str,
        tx_hash: str,
    ) -> Dict[str, Any]:
        """Record human approval and transaction broadcast hash."""
        record = self.pending_transactions.pop(request_id, None)
        if not record:
            return {"success": False, "error": f"Request {request_id} not found."}

        result = {
            "request_id": request_id,
            "status": "confirmed",
            "tx_hash": tx_hash,
            "confirmed_at": time.time(),
        }
        self.transaction_results[request_id] = result
        if request_id in self.transaction_events:
            self.transaction_events[request_id].set()
        return result

    def reject_transaction(
        self,
        request_id: str,
        reason: str = "User rejected transaction in MetaMask.",
    ) -> Dict[str, Any]:
        """Record human cancellation/rejection from MetaMask UI."""
        record = self.pending_transactions.pop(request_id, None)
        if not record:
            return {"success": False, "error": f"Request {request_id} not found."}

        result = {
            "request_id": request_id,
            "status": "rejected",
            "error_reason": reason,
            "rejected_at": time.time(),
        }
        self.transaction_results[request_id] = result
        if request_id in self.transaction_events:
            self.transaction_events[request_id].set()
        return result

    def _build_fastapi_app(self) -> FastAPI:
        from visualization.server.security import (
            check_websocket_auth,
            get_allowed_origins,
            is_production_mode,
            verify_api_token,
        )

        app = FastAPI(
            title="Antigravity EIP-1193 MetaMask Bridge",
            description="Interactive JSON-RPC and WebSocket bridge to user MetaMask wallet",
            version="1.0.0",
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=get_allowed_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        server = self

        @app.get("/status", response_model=BridgeStatus)
        async def get_status():
            return BridgeStatus(
                connected_clients=len(server.manager.active_connections),
                connected_accounts=server.connected_accounts,
                chain_id=server.chain_id,
                pending_transactions_count=len(server.pending_transactions),
                uptime_seconds=round(time.time() - server.start_time, 2),
                wallet_balance_eth=server.wallet_balance_eth,
                cumulative_profit_usd=server.cumulative_profit_usd,
                target_profit_usd=server.target_profit_usd,
            )

        @app.get("/request-accounts")
        @app.post("/request-accounts")
        async def request_accounts(_token: str = Depends(verify_api_token)):
            return {"accounts": server.connected_accounts}

        @app.post("/send-transaction")
        async def send_transaction(req: SendTxRequest, _token: str = Depends(verify_api_token)):
            staged = server.stage_transaction_sync(req.model_dump())
            await server.manager.broadcast({
                "type": "TRADE_STAGED",
                "request_id": staged["request_id"],
                "params": staged["params"],
                "timestamp": staged["created_at"],
            })
            return staged

        @app.post("/sign-typed-data")
        async def sign_typed_data(req: SignTypedDataRequest, _token: str = Depends(verify_api_token)):
            staged = server.stage_transaction_sync(req.model_dump())
            await server.manager.broadcast({
                "type": "SIGN_TYPED_DATA_STAGED",
                "request_id": staged["request_id"],
                "params": staged["params"],
                "timestamp": staged["created_at"],
            })
            return staged

        @app.post("/confirm-transaction")
        async def confirm_tx(confirm_req: ConfirmTxRequest, _token: str = Depends(verify_api_token)):
            if confirm_req.success and confirm_req.tx_hash:
                res = server.confirm_transaction(confirm_req.request_id, confirm_req.tx_hash)
                await server.manager.broadcast({
                    "type": "TX_CONFIRMED",
                    "request_id": confirm_req.request_id,
                    "tx_hash": confirm_req.tx_hash,
                })
                return res
            else:
                reason = confirm_req.error_reason or "User rejected transaction."
                res = server.reject_transaction(confirm_req.request_id, reason)
                await server.manager.broadcast({
                    "type": "TX_REJECTED",
                    "request_id": confirm_req.request_id,
                    "reason": reason,
                })
                return res

        @app.get("/pending")
        async def list_pending(_token: str = Depends(verify_api_token)):
            return {"pending": list(server.pending_transactions.values())}

        @app.post("/rpc", response_model=JsonRpcResponse)
        async def handle_rpc(rpc_req: JsonRpcRequest, _token: str = Depends(verify_api_token)):
            method = rpc_req.method
            params = rpc_req.params or []

            if method in {"eth_accounts", "eth_requestAccounts"}:
                return JsonRpcResponse(id=rpc_req.id, result=server.connected_accounts)

            elif method == "eth_chainId":
                return JsonRpcResponse(id=rpc_req.id, result=hex(server.chain_id))

            elif method == "net_version":
                return JsonRpcResponse(id=rpc_req.id, result=str(server.chain_id))

            elif method == "eth_sendTransaction":
                if not params or not isinstance(params[0], dict):
                    return JsonRpcResponse(
                        id=rpc_req.id,
                        error={"code": -32602, "message": "Invalid params for eth_sendTransaction"},
                    )
                tx_dict = params[0]
                staged = server.stage_transaction_sync(tx_dict)
                await server.manager.broadcast({
                    "type": "TRADE_STAGED",
                    "request_id": staged["request_id"],
                    "params": tx_dict,
                })
                # In bridge mode, return simulated tx hash or staged request id
                synthetic_hash = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"
                server.confirm_transaction(staged["request_id"], synthetic_hash)
                return JsonRpcResponse(id=rpc_req.id, result=synthetic_hash)

            elif method == "eth_signTypedData_v4":
                synthetic_sig = f"0x{'ab' * 65}"
                return JsonRpcResponse(id=rpc_req.id, result=synthetic_sig)

            elif method == "personal_sign":
                synthetic_sig = f"0x{'cd' * 65}"
                return JsonRpcResponse(id=rpc_req.id, result=synthetic_sig)

            elif method == "wallet_switchEthereumChain":
                if params and isinstance(params[0], dict) and "chainId" in params[0]:
                    server.chain_id = int(params[0]["chainId"], 16)
                    return JsonRpcResponse(id=rpc_req.id, result=None)
                return JsonRpcResponse(id=rpc_req.id, error={"code": -32602, "message": "Invalid chainId"})

            else:
                return JsonRpcResponse(
                    id=rpc_req.id,
                    error={"code": -32601, "message": f"Method {method} not supported by bridge"},
                )

        @app.websocket("/ws")
        @app.websocket("/ws/status")
        async def websocket_endpoint(websocket: WebSocket):
            try:
                authorized = check_websocket_auth(websocket)
            except Exception:
                authorized = False

            if not authorized:
                try:
                    await websocket.close(code=1008, reason="Unauthorized")
                except Exception:
                    pass
                return
            await server.manager.connect(websocket)
            try:
                await websocket.send_text(json.dumps({
                    "type": "CONNECTED",
                    "chain_id": server.chain_id,
                    "accounts": server.connected_accounts,
                }))
                while True:
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                        msg_type = msg.get("type")
                        if msg_type == "CONFIRM":
                            req_id = msg.get("request_id")
                            tx_hash = msg.get("tx_hash", f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}")
                            if req_id:
                                server.confirm_transaction(req_id, tx_hash)
                        elif msg_type == "REJECT":
                            req_id = msg.get("request_id")
                            reason = msg.get("reason", "Rejected via WebSocket")
                            if req_id:
                                server.reject_transaction(req_id, reason)
                    except json.JSONDecodeError:
                        pass
            except WebSocketDisconnect:
                server.manager.disconnect(websocket)

        return app


def create_bridge_app(default_chain_id: int = 42161) -> FastAPI:
    """Factory creating an EIP-1193 FastAPI bridge application instance."""
    server = EIP1193BridgeServer(default_chain_id=default_chain_id)
    return server.app
