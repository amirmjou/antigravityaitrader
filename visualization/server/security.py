"""
Security and authentication gateway for trading visualization server and Web3 bridges (Milestone 6).
Enforces dual-mode (development vs production) access control, constant-time API key validation,
strict CORS origin filtering, HTTP security headers, and DoS rate limiting.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)

# Reusable HTTPBearer security scheme (auto_error=False allows query param and X-API-Key fallback)
bearer_scheme = HTTPBearer(auto_error=False)


def is_production_mode() -> bool:
    """Returns True if TRADINGAGENTS_SECURITY_MODE is set to 'production'."""
    mode = os.environ.get("TRADINGAGENTS_SECURITY_MODE", "development").strip().lower()
    return mode == "production"


def is_auth_enforced() -> bool:
    """Returns True if running in production mode or if TRADING_API_KEY is configured."""
    return is_production_mode() or bool(os.environ.get("TRADING_API_KEY"))


def get_configured_api_key() -> Optional[str]:
    """Retrieves the configured API key secret from environment."""
    return os.environ.get("TRADING_API_KEY")


def get_allowed_origins() -> List[str]:
    """
    Returns the list of allowed CORS origins.
    Configured via comma-separated ALLOWED_ORIGINS env var.
    """
    raw = os.environ.get("ALLOWED_ORIGINS")
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8899",
        "http://127.0.0.1:8899",
    ]


def verify_token_string(token: Optional[str]) -> bool:
    """
    Validates a token against configured secret using constant-time comparison.
    Safely encodes strings to UTF-8 bytes to prevent non-ASCII TypeErrors in compare_digest.
    """
    if not is_auth_enforced():
        return True
    expected = get_configured_api_key()
    if not expected or not token:
        return False
    try:
        token_bytes = token.encode("utf-8") if isinstance(token, str) else bytes(token)
        expected_bytes = expected.encode("utf-8") if isinstance(expected, str) else bytes(expected)
        return hmac.compare_digest(token_bytes, expected_bytes)
    except (TypeError, UnicodeEncodeError, Exception):
        return False


async def verify_api_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> str:
    """
    FastAPI dependency enforcing API authentication on protected endpoints.
    In development mode without an API key configured, allows bypass.
    In production mode (or when TRADING_API_KEY is set), verifies Bearer token,
    X-API-Key header, or ?token= query parameter.
    """
    if not is_auth_enforced():
        return "development_bypass"

    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "x-api-key" in request.headers:
        token = request.headers["x-api-key"]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token or not verify_token_string(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def check_websocket_auth(websocket: WebSocket) -> bool:
    """
    Validates authentication for incoming WebSocket connections.
    Checks query parameter ?token=<TOKEN> or Authorization / X-API-Key headers.
    Catches all exceptions to ensure clean boolean return on malformed tokens.
    """
    if not is_auth_enforced():
        return True

    try:
        token: Optional[str] = websocket.query_params.get("token")
        if not token:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            elif "x-api-key" in websocket.headers:
                token = websocket.headers.get("x-api-key")

        return verify_token_string(token)
    except Exception as e:
        logger.debug("check_websocket_auth exception: %s", e)
        return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects strict production HTTP security headers onto all responses:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: default-src 'self'; connect-src 'self' wss: https:; script-src 'self'; style-src 'self' 'unsafe-inline'
    - Referrer-Policy: strict-origin-when-cross-origin
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' wss: https:; script-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class RateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter for DoS protection.
    """

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, max_requests: int, window_seconds: float = 60.0) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._requests[key]
            cutoff = now - window_seconds
            valid = [t for t in timestamps if t > cutoff]
            if len(valid) >= max_requests:
                self._requests[key] = valid
                return False
            valid.append(now)
            self._requests[key] = valid
            return True

    def reset(self):
        """Clears all stored rate limit history."""
        with self._lock:
            self._requests.clear()


# Global rate limiter instance
global_rate_limiter = RateLimiter()


def rate_limit_dependency(max_requests: int, window_seconds: float = 60.0, category: str = "general"):
    """
    Factory creating a FastAPI dependency enforcing rate limits per client IP.
    """

    def _limiter(request: Request):
        client_ip = request.client.host if request.client else "127.0.0.1"
        key = f"{category}:{client_ip}"
        if not global_rate_limiter.is_allowed(key, max_requests=max_requests, window_seconds=window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too Many Requests",
            )
        return True

    return _limiter


class SimulationCache:
    """
    In-memory TTL cache for expensive simulation runs to prevent CPU exhaustion.
    """

    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            if key in self._cache:
                ts, val = self._cache[key]
                if now - ts < self.ttl_seconds:
                    return val
                del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        with self._lock:
            self._cache[key] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._cache.clear()


global_simulation_cache = SimulationCache(ttl_seconds=60.0)
