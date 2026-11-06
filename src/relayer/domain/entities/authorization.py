"""EIP-3009 authorization value object.

Groups the components of a transfer-with-authorization signature.
Validates only structural invariants. Cryptographic verification
of the signature belongs to a SignatureVerifier port implemented
by the infrastructure layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.domain.exceptions import InvalidAuthorizationError
from relayer.domain.value_objects import Address, Amount, Nonce, Signature


@dataclass(frozen=True, slots=True)
class Authorization:
    """A structurally valid EIP-3009 authorization."""

    from_address: Address
    to_address: Address
    value: Amount
    valid_after: int
    valid_before: int
    nonce: Nonce
    signature: Signature

    def __post_init__(self) -> None:
        if self.from_address.is_zero:
            raise InvalidAuthorizationError("from_address cannot be zero")
        if self.to_address.is_zero:
            raise InvalidAuthorizationError("to_address cannot be zero")
        if self.from_address == self.to_address:
            raise InvalidAuthorizationError(
                "from_address and to_address must differ"
            )
        if self.value.is_zero:
            raise InvalidAuthorizationError("value cannot be zero")
        if self.valid_after >= self.valid_before:
            raise InvalidAuthorizationError(
                f"valid_after ({self.valid_after}) must be < "
                f"valid_before ({self.valid_before})"
            )

    # --- Time window queries (pure, no side effects) ---------------------

    def is_expired(self, now: int) -> bool:
        """Mirrors the contract check `block.timestamp < validBefore`."""
        return now >= self.valid_before

    def is_not_yet_valid(self, now: int) -> bool:
        """Mirrors the contract check `block.timestamp > validAfter`."""
        return now <= self.valid_after

    def is_valid_at(self, now: int) -> bool:
        return self.valid_after < now < self.valid_before
