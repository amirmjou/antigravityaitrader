"""HTTP helpers shared by the vendors."""

import re
from typing import List, Optional
import requests

RE_ALCHEMY_URL = re.compile(r"(https?://[a-zA-Z0-9.-]*alchemy\.com/v2/)[a-zA-Z0-9_-]+", re.IGNORECASE)
RE_INFURA_URL = re.compile(r"(https?://[a-zA-Z0-9.-]*infura\.io/v3/)[a-zA-Z0-9_-]+", re.IGNORECASE)
RE_QUICKNODE_URL = re.compile(r"(https?://[a-zA-Z0-9.-]*quiknode\.pro/)[a-zA-Z0-9_-]+", re.IGNORECASE)
RE_URL_QUERY_SECRETS = re.compile(r"([?&](?:apikey|api_key|key|token|secret|password)=)[^&\s'\"]+", re.IGNORECASE)
RE_BEARER_AUTH = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE)
RE_PRIVATE_KEY_HEX = re.compile(r"\b0x[a-fA-F0-9]{64}\b")


def scrub_secrets(text: str) -> str:
    """
    Scrubs private keys, API keys, and credential-embedded RPC URLs from text/tracebacks.
    """
    if not text:
        return text
    scrubbed = str(text)
    scrubbed = RE_ALCHEMY_URL.sub(r"\1REDACTED", scrubbed)
    scrubbed = RE_INFURA_URL.sub(r"\1REDACTED", scrubbed)
    scrubbed = RE_QUICKNODE_URL.sub(r"\1REDACTED", scrubbed)
    scrubbed = RE_URL_QUERY_SECRETS.sub(r"\1REDACTED", scrubbed)
    scrubbed = RE_BEARER_AUTH.sub(r"\1REDACTED", scrubbed)
    scrubbed = RE_PRIVATE_KEY_HEX.sub("0x***REDACTED_PRIVATE_KEY***", scrubbed)
    return scrubbed


def sanitize_secret_trace(error_msg: str, secrets: Optional[List[str]] = None) -> str:
    """
    Redacts known secrets and tokens from error messages and tracebacks.
    """
    if not error_msg:
        return error_msg
    sanitized = str(error_msg)
    if secrets:
        for secret in secrets:
            if secret and len(secret) >= 4:
                sanitized = sanitized.replace(secret, "***REDACTED***")
    return scrub_secrets(sanitized)


def get_scrubbed(url: str, *, params: dict, timeout: float, secret: str, passthrough=()):
    """``requests.get`` plus ``raise_for_status``, with ``secret`` kept out of errors.

    Vendors that authenticate with a query parameter put the key in the URL, and
    requests quotes the full URL in HTTP, connection and timeout errors, so any
    log or traceback that records one would carry the key (#1324). A requests
    error is re-raised as the same class with the key replaced and nothing
    attached: no request or response (both hold the URL) and no exception chain,
    which is why this raises after the ``except`` block rather than inside it.
    Statuses in ``passthrough`` are returned for the caller to handle.
    """
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code not in passthrough:
            response.raise_for_status()
        return response
    except requests.RequestException as exc:
        error = type(exc)(str(exc).replace(secret, "***")) if secret else exc
    raise error


def vendor_reachable(url: str, timeout: float = 5.0) -> bool:
    """Whether the vendor answers at all, for telling silence from an outage.

    A client that returns an empty result instead of raising leaves those two
    cases indistinguishable. Called only when a result is empty.
    """
    try:
        requests.head(url, timeout=timeout, allow_redirects=True)
        return True
    except requests.RequestException:
        return False
