"""EIP-3009 authorization nonce value object.

A nonce is exactly 32 bytes (bytes32 in the EVM). It is generated
randomly off-chain and consumed exactly once per authorization.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.domain.exceptions import InvalidNonceError

NONCE_SIZE = 32


@dataclass(frozen=True, slots=True)
class Nonce:
    """A 32-byte authorization nonce."""

    value: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.value, bytes):
            raise InvalidNonceError(
                f"Nonce must be bytes, got {type(self.value).__name__}"
            )
        if len(self.value) != NONCE_SIZE:
            raise InvalidNonceError(
                f"Nonce must be exactly {NONCE_SIZE} bytes, got {len(self.value)}"
            )

    @classmethod
    def from_hex(cls, hex_str: str) -> Nonce:
        """Parse a hex string (with or without '0x' prefix)."""
        s = hex_str.strip().lower()
        if s.startswith("0x"):
            s = s[2:]
        try:
            raw = bytes.fromhex(s)
        except ValueError as e:
            raise InvalidNonceError(f"Invalid hex string for nonce: {hex_str}") from e
        return cls(value=raw)

    def to_hex(self) -> str:
        return "0x" + self.value.hex()

    def __str__(self) -> str:
        return self.to_hex()
