"""Authorization policy value object.

Aggregates the configurable rules that constrain which authorizations
the relayer is willing to sponsor. Immutable and self-validating.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.domain.exceptions import InvalidPolicyError
from relayer.domain.value_objects.address import Address
from relayer.domain.value_objects.amount import Amount


@dataclass(frozen=True, slots=True)
class Policy:
    """Configurable constraints applied to every authorization."""

    max_value: Amount
    max_validity_window_seconds: int
    min_remaining_validity_seconds: int
    allowed_destinations: frozenset[Address] | None = None

    def __post_init__(self) -> None:
        if self.max_validity_window_seconds <= 0:
            raise InvalidPolicyError(
                "max_validity_window_seconds must be positive"
            )
        if self.min_remaining_validity_seconds < 0:
            raise InvalidPolicyError(
                "min_remaining_validity_seconds cannot be negative"
            )
        if self.min_remaining_validity_seconds >= self.max_validity_window_seconds:
            raise InvalidPolicyError(
                "min_remaining_validity_seconds must be less than "
                "max_validity_window_seconds (otherwise the policy "
                "is unsatisfiable by construction)"
            )

    def is_destination_allowed(self, destination: Address) -> bool:
        if self.allowed_destinations is None:
            return True
        return destination in self.allowed_destinations
