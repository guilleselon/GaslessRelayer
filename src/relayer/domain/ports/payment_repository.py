"""Payment repository port.

Persistence and idempotency contract for PaymentRequest entities.
Implementations must guarantee atomicity for claim_pending and
uniqueness on (from_address, nonce).
"""

from __future__ import annotations

from typing import Protocol

from relayer.domain.entities import PaymentRequest
from relayer.domain.value_objects import Address, Nonce


class PaymentRepository(Protocol):
    """Persistence boundary for PaymentRequest aggregates."""

    def save_new(self, payment: PaymentRequest) -> PaymentRequest:
        """Insert a new payment and return it with its assigned id.

        Must raise DuplicatePaymentError if a payment with the same
        (from_address, nonce) already exists.

        The input entity must be in PENDING status.
        """
        ...

    def save(self, payment: PaymentRequest) -> None:
        """Persist a state change of an existing payment.

        Must raise InvalidStateTransitionError if the payment.id does
        not correspond to an existing record, or if the new status is
        not a legal successor of the persisted one.
        """
        ...

    def get_by_id(self, payment_id: int) -> PaymentRequest | None:
        """Return the payment with the given id, or None if not found."""
        ...

    def get_by_from_and_nonce(
        self, from_address: Address, nonce: Nonce
    ) -> PaymentRequest | None:
        """Return the payment with the given (from, nonce), or None.

        Used for idempotency: before creating a new record, the
        application checks whether the same authorization has already
        been submitted.
        """
        ...

    def claim_pending(self, limit: int, now: int) -> list[PaymentRequest]:
        """Atomically claim up to `limit` PENDING payments for processing.

        Guarantees:
          - Each returned payment is claimed by exactly one caller,
            even with concurrent workers.
          - Returned payments are already in PROCESSING status and
            persisted with updated_at = now.
          - Order is oldest first (by id).
          - Returns an empty list if there are no pending payments.
        """
        ...
