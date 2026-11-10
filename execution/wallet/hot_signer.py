"""
Hot Keystore Signer using eth-account.
Supports encrypted keystore handling, private key management, nonce tracking,
EIP-1559 gas fee estimation, and transaction/message signing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_defunct, encode_typed_data


class HotKeystoreSigner:
    """
    Autonomous hot keystore signer for on-chain execution.
    Manages private keys securely via eth-account, tracks local transaction nonces,
    estimates EIP-1559 priority & max fees, and produces signed raw transactions.
    """

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

    @property
    def address(self) -> str:
        """Returns the checksummed Ethereum address."""
        return self._account.address

    @property
    def private_key_hex(self) -> str:
        """Returns the 0x-prefixed private key in hex."""
        h = self._account.key.hex()
        return h if h.startswith("0x") else "0x" + h

    @property
    def masked_private_key(self) -> str:
        """Returns masked private key representation (e.g. 0x1234...abcd)."""
        k = self.private_key_hex
        if len(k) > 10:
            return f"{k[:6]}...{k[-4:]}"
        return "0x***"

    def __repr__(self) -> str:
        return f"<HotKeystoreSigner address={self.address} chain_id={self.default_chain_id} key={self.masked_private_key}>"

    def __str__(self) -> str:
        return f"<HotKeystoreSigner address={self.address} chain_id={self.default_chain_id}>"

    @classmethod
    def from_private_key(
        cls,
        private_key: Union[str, bytes],
        web3_provider: Optional[Any] = None,
        default_chain_id: int = 42161,
    ) -> HotKeystoreSigner:
        """Initialize signer from a raw private key hex string or bytes."""
        account = Account.from_key(private_key)
        return cls(account=account, web3_provider=web3_provider, default_chain_id=default_chain_id)

    @classmethod
    def create_new(
        cls,
        extra_entropy: str = "",
        web3_provider: Optional[Any] = None,
        default_chain_id: int = 42161,
    ) -> HotKeystoreSigner:
        """Generate a fresh random Ethereum account."""
        account = Account.create(extra_entropy=extra_entropy)
        return cls(account=account, web3_provider=web3_provider, default_chain_id=default_chain_id)

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

    @classmethod
    def from_keystore_file(
        cls,
        file_path: Union[str, Path],
        password: str,
        web3_provider: Optional[Any] = None,
        default_chain_id: int = 42161,
    ) -> HotKeystoreSigner:
        """Read and decrypt an encrypted keystore from disk."""
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            keystore_data = json.load(f)
        return cls.from_keystore_json(
            keystore_data=keystore_data,
            password=password,
            web3_provider=web3_provider,
            default_chain_id=default_chain_id,
        )

    def export_keystore(self, password: str, kdf: str = "scrypt") -> Dict[str, Any]:
        """Encrypt account private key into standard Ethereum JSON Keystore (V3)."""
        return Account.encrypt(self._account.key, password, kdf=kdf)

    def save_keystore_file(
        self,
        file_path: Union[str, Path],
        password: str,
        kdf: str = "scrypt",
    ) -> Path:
        """Save encrypted keystore to target file path with strict POSIX 0600 permissions."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        keystore_dict = self.export_keystore(password, kdf=kdf)
        content = json.dumps(keystore_dict, indent=2).encode("utf-8")

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY

        fd = os.open(str(path), flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass

        return path

    def get_nonce(self) -> int:
        """
        Get next sequential nonce for the account.
        If internal nonce is not initialized and a web3 provider is configured,
        fetches pending transaction count from the node.
        """
        if self._nonce is None:
            if self.w3 is not None and hasattr(self.w3, "eth"):
                try:
                    self._nonce = self.w3.eth.get_transaction_count(self.address, "pending")
                except Exception:
                    self._nonce = 0
            else:
                self._nonce = 0
        return self._nonce

    def set_nonce(self, nonce: int) -> None:
        """Explicitly override the local nonce tracker."""
        self._nonce = nonce

    def resync_nonce(self) -> int:
        """Force synchronize nonce from the connected Web3 provider."""
        if self.w3 is not None and hasattr(self.w3, "eth"):
            self._nonce = self.w3.eth.get_transaction_count(self.address, "pending")
        else:
            self._nonce = 0
        return self._nonce

    def estimate_eip1559_fees(
        self,
        base_fee_gwei: Optional[float] = None,
        priority_fee_gwei: Optional[float] = None,
        max_priority_cap_gwei: float = 2.0,
    ) -> Dict[str, int]:
        """
        Estimate EIP-1559 fee parameters (maxPriorityFeePerGas and maxFeePerGas in wei).
        maxFeePerGas = (2 * baseFeePerGas) + maxPriorityFeePerGas
        """
        # Determine base fee in gwei
        if base_fee_gwei is None:
            if self.w3 is not None:
                if hasattr(self.w3, "base_fee_gwei"):
                    base_fee_gwei = float(self.w3.base_fee_gwei)
                elif hasattr(self.w3, "eth"):
                    try:
                        latest_block = self.w3.eth.get_block("latest")
                        base_fee_wei = latest_block.get("baseFeePerGas", 100_000_000)
                        base_fee_gwei = base_fee_wei / 1e9
                    except Exception:
                        base_fee_gwei = 0.1
                else:
                    base_fee_gwei = 0.1
            else:
                base_fee_gwei = 0.1

        # Determine priority fee in gwei
        if priority_fee_gwei is None:
            if self.w3 is not None:
                if hasattr(self.w3, "priority_fee_gwei"):
                    priority_fee_gwei = float(self.w3.priority_fee_gwei)
                elif hasattr(self.w3, "eth"):
                    try:
                        p_fee_wei = self.w3.eth.max_priority_fee
                        priority_fee_gwei = min(p_fee_wei / 1e9, max_priority_cap_gwei)
                    except Exception:
                        priority_fee_gwei = 0.05
                else:
                    priority_fee_gwei = 0.05
            else:
                priority_fee_gwei = 0.05

        priority_fee_gwei = min(priority_fee_gwei, max_priority_cap_gwei)
        base_fee_wei = int(base_fee_gwei * 1e9)
        priority_fee_wei = int(priority_fee_gwei * 1e9)
        max_fee_wei = (2 * base_fee_wei) + priority_fee_wei

        return {
            "maxPriorityFeePerGas": priority_fee_wei,
            "maxFeePerGas": max_fee_wei,
            "baseFeePerGas": base_fee_wei,
        }

    def sign_transaction(self, tx_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Signs an EVM transaction dictionary (EIP-1559 type 2 or legacy).
        Auto-populates from address, chainId, nonce, and EIP-1559 fees if missing.
        """
        prepared_tx = dict(tx_dict)

        if "from" not in prepared_tx:
            prepared_tx["from"] = self.address

        if "chainId" not in prepared_tx:
            prepared_tx["chainId"] = self.default_chain_id

        if "nonce" not in prepared_tx:
            prepared_tx["nonce"] = self.get_nonce()

        # Populate EIP-1559 fields if not legacy gasPrice
        if "gasPrice" not in prepared_tx and "maxFeePerGas" not in prepared_tx:
            fees = self.estimate_eip1559_fees()
            prepared_tx["maxFeePerGas"] = fees["maxFeePerGas"]
            prepared_tx["maxPriorityFeePerGas"] = fees["maxPriorityFeePerGas"]
            prepared_tx["type"] = 2

        signed = self._account.sign_transaction(prepared_tx)

        # Advance local nonce
        if self._nonce is not None:
            self._nonce += 1

        raw_tx_bytes = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        raw_tx_hex = raw_tx_bytes.hex() if isinstance(raw_tx_bytes, bytes) else str(raw_tx_bytes)
        if not raw_tx_hex.startswith("0x"):
            raw_tx_hex = "0x" + raw_tx_hex

        tx_hash_bytes = getattr(signed, "hash", None)
        tx_hash_hex = tx_hash_bytes.hex() if isinstance(tx_hash_bytes, bytes) else str(tx_hash_bytes)
        if not tx_hash_hex.startswith("0x"):
            tx_hash_hex = "0x" + tx_hash_hex

        return {
            "raw_transaction": raw_tx_hex,
            "tx_hash": tx_hash_hex,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
            "nonce": prepared_tx["nonce"],
            "signed_obj": signed,
        }

    def sign_message(self, message: Union[str, bytes]) -> Dict[str, Any]:
        """Signs an EIP-191 personal message."""
        if isinstance(message, str):
            encoded = encode_defunct(text=message)
        else:
            encoded = encode_defunct(primitive=message)

        signed = self._account.sign_message(encoded)
        sig = signed.signature.hex() if hasattr(signed.signature, "hex") else str(signed.signature)
        if not sig.startswith("0x"):
            sig = "0x" + sig
        m_hash = signed.message_hash.hex() if hasattr(signed.message_hash, "hex") else str(signed.message_hash)
        if not m_hash.startswith("0x"):
            m_hash = "0x" + m_hash
        return {
            "signature": sig,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
            "message_hash": m_hash,
        }

    def sign_typed_data(
        self,
        domain_data: Optional[Dict[str, Any]] = None,
        message_types: Optional[Dict[str, Any]] = None,
        message_data: Optional[Dict[str, Any]] = None,
        full_message: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Signs EIP-712 structured typed data."""
        if full_message is not None:
            encoded = encode_typed_data(full_message=full_message)
        else:
            filtered_types = dict(message_types or {})
            filtered_types.pop("EIP712Domain", None)
            encoded = encode_typed_data(
                domain_data=domain_data,
                message_types=filtered_types,
                message_data=message_data,
            )
        signed = self._account.sign_message(encoded)
        sig = signed.signature.hex() if hasattr(signed.signature, "hex") else str(signed.signature)
        if not sig.startswith("0x"):
            sig = "0x" + sig
        m_hash = signed.message_hash.hex() if hasattr(signed.message_hash, "hex") else str(signed.message_hash)
        if not m_hash.startswith("0x"):
            m_hash = "0x" + m_hash
        return {
            "signature": sig,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
            "message_hash": m_hash,
        }
