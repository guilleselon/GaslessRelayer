"""PaymentRequest entity: the aggregate root of the payment lifecycle.

Immutable. State transitions return new instances, leaving the
previous one untouched. This makes the lifecycle auditable and safe
under concurrency (no shared mutable state).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from relayer.domain.entities.authorization import Authorization
from relayer.domain.exceptions import InvalidStateTransitionError


class PaymentStatus(str, Enum):
    """Lifecycle states of a payment request."""

    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FAILED = "failed"


# Explicit transition table. Extend here to add new states.
_ALLOWED_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.PENDING: {PaymentStatus.PROCESSING, PaymentStatus.FAILED},
    PaymentStatus.PROCESSING: {PaymentStatus.CONFIRMED, PaymentStatus.FAILED},
    PaymentStatus.CONFIRMED: set(),   # terminal
    PaymentStatus.FAILED: set(),      # terminal
}


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    """The aggregate root of a gasless payment."""

    id: int | None
    authorization: Authorization
    status: PaymentStatus
    tx_hash: str | None
    block_number: int | None
    error: str | None
    created_at: int
    updated_at: int

    # --- Factory ---------------------------------------------------------

    @classmethod
    def create(cls, authorization: Authorization, now: int) -> PaymentRequest:
        return cls(
            id=None,
            authorization=authorization,
            status=PaymentStatus.PENDING,
            tx_hash=None,
            block_number=None,
            error=None,
            created_at=now,
            updated_at=now,
        )

    # --- Transition machinery --------------------------------------------

    def _transition(
        self, new_status: PaymentStatus, now: int, **changes: object
    ) -> PaymentRequest:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition from '{self.status.value}' "
                f"to '{new_status.value}'"
            )
        return replace(self, status=new_status, updated_at=now, **changes)

    # --- Public transitions ----------------------------------------------

    def mark_processing(self, now: int) -> PaymentRequest:
        return self._transition(PaymentStatus.PROCESSING, now)

    def mark_confirmed(
        self, tx_hash: str, block_number: int, now: int
    ) -> PaymentRequest:
        if not tx_hash:
            raise InvalidStateTransitionError("tx_hash is required for CONFIRMED")
        if not isinstance(block_number, int) or block_number < 0:
            raise InvalidStateTransitionError(
                "block_number must be a non-negative integer"
            )
        return self._transition(
            PaymentStatus.CONFIRMED,
            now,
            tx_hash=tx_hash,
            block_number=block_number,
        )

    def mark_failed(
        self, error: str, now: int, tx_hash: str | None = None
    ) -> PaymentRequest:
        if not error:
            raise InvalidStateTransitionError("error message is required for FAILED")
        changes: dict[str, object] = {"error": error}
        if tx_hash is not None:
            changes["tx_hash"] = tx_hash
        return self._transition(PaymentStatus.FAILED, now, **changes)

    # --- Queries ---------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.status in (PaymentStatus.CONFIRMED, PaymentStatus.FAILED)
