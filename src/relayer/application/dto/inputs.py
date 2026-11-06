"""Input DTOs: raw primitives from external callers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubmitPaymentInput:
    """Input for submitting an EIP-3009 authorization."""

    from_address: str
    to_address: str
    value_raw: str          # atomic units as decimal string
    valid_after: int
    valid_before: int
    nonce: str              # 0x-prefixed hex, 32 bytes
    v: int
    r: str                  # 0x-prefixed hex, 32 bytes
    s: str                  # 0x-prefixed hex, 32 bytes
