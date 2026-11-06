"""ECDSA signature value object (65-byte format).

Normalizes v to 27/28 (EVM ecrecover convention). Rejects EIP-155
signatures because they are not valid for EIP-712 typed data.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.domain.exceptions import InvalidSignatureError

SIGNATURE_SIZE = 65
COMPONENT_SIZE = 32


@dataclass(frozen=True, slots=True)
class Signature:
    """An ECDSA signature over an EIP-712 digest."""

    v: int
    r: bytes
    s: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.v, int) or isinstance(self.v, bool):
            raise InvalidSignatureError(
                f"v must be int, got {type(self.v).__name__}"
            )
        if self.v not in (0, 1, 27, 28):
            raise InvalidSignatureError(
                f"v must be in {{0, 1, 27, 28}} (EIP-712), got {self.v}"
            )
        object.__setattr__(self, "v", self.v + 27 if self.v < 27 else self.v)

        if not isinstance(self.r, bytes) or len(self.r) != COMPONENT_SIZE:
            raise InvalidSignatureError("r must be 32 bytes")
        if not isinstance(self.s, bytes) or len(self.s) != COMPONENT_SIZE:
            raise InvalidSignatureError("s must be 32 bytes")

    @classmethod
    def from_bytes(cls, raw: bytes) -> Signature:
        if not isinstance(raw, bytes):
            raise InvalidSignatureError(
                f"raw signature must be bytes, got {type(raw).__name__}"
            )
        if len(raw) != SIGNATURE_SIZE:
            raise InvalidSignatureError(
                f"raw signature must be {SIGNATURE_SIZE} bytes, got {len(raw)}"
            )
        return cls(r=raw[0:32], s=raw[32:64], v=raw[64])

    def to_bytes(self) -> bytes:
        return self.r + self.s + bytes([self.v])

    def __str__(self) -> str:
        return (
            f"Signature(v={self.v}, "
            f"r=0x{self.r.hex()[:8]}..., s=0x{self.s.hex()[:8]}...)"
        )
