"""Ethereum address value object.

Stores the address as lowercase hex without EIP-55 checksum.
Checksum formatting is a presentation concern handled by the
infrastructure layer, not the domain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from relayer.domain.exceptions import InvalidAddressError

_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
_ZERO_ADDRESS = "0x" + "0" * 40


@dataclass(frozen=True, slots=True)
class Address:
    """A validated Ethereum address (20 bytes)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidAddressError(
                f"Address must be a string, got {type(self.value).__name__}"
            )
        normalized = self.value.strip().lower()
        if not normalized.startswith("0x"):
            normalized = "0x" + normalized
        if not _ADDRESS_PATTERN.match(normalized):
            raise InvalidAddressError(f"Invalid Ethereum address: {self.value}")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def zero(cls) -> Address:
        return cls(value=_ZERO_ADDRESS)

    @property
    def is_zero(self) -> bool:
        return self.value == _ZERO_ADDRESS

    def to_bytes(self) -> bytes:
        """Return the raw 20-byte representation (useful for EIP-712 hashing)."""
        return bytes.fromhex(self.value[2:])

    def __str__(self) -> str:
        return self.value
