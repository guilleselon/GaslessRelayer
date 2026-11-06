"""Payment executor.

Converts a claimed PaymentRequest (in PROCESSING) into a terminal
state (CONFIRMED or FAILED) by driving the ChainGateway port.

Guarantees:
  - Never returns a PaymentRequest in PROCESSING.
  - Never mutates the input entity (frozen).
  - Records the tx_hash whenever it exists, even on failure.
"""

from __future__ import annotations

from relayer.domain.entities import PaymentRequest, PaymentStatus
from relayer.domain.exceptions import InvalidStateTransitionError
from relayer.domain.ports import ChainGateway


class PaymentExecutor:
    """Drives the on-chain execution of a claimed payment."""

    def __init__(self, chain: ChainGateway) -> None:
        self._chain = chain

    def execute(self, payment: PaymentRequest, now: int) -> PaymentRequest:
        """Execute the payment and return it in a terminal state.

        Preconditions:
          payment.status == PROCESSING
          payment.id is not None  (i.e., it has been persisted)

        The returned entity is either CONFIRMED or FAILED. It is
        NOT persisted by this method; the caller (use case) is
        responsible for calling repository.save(result).
        """
        if payment.status != PaymentStatus.PROCESSING:
            raise InvalidStateTransitionError(
                f"PaymentExecutor requires PROCESSING, got '{payment.status.value}'"
            )

        auth = payment.authorization

        # --- 1. Pre-flight: is the nonce already consumed on-chain? -----
        try:
            if self._chain.is_nonce_used(auth.from_address, auth.nonce):
                return payment.mark_failed(
                    "Authorization nonce already consumed on-chain "
                    "(front-run, replay, or previously executed)",
                    now,
                )
        except Exception as e:
            return payment.mark_failed(
                f"Pre-flight nonce check failed: {type(e).__name__}: {e}",
                now,
            )

        # --- 2. Submit the on-chain transaction -------------------------
        tx_hash: str
        try:
            tx_hash = self._chain.transfer_with_authorization(auth)
        except Exception as e:
            return payment.mark_failed(
                f"Transaction submission failed: {type(e).__name__}: {e}",
                now,
            )

        # --- 3. Wait for confirmation ----------------------------------
        try:
            receipt = self._chain.wait_for_confirmation(tx_hash)
        except Exception as e:
            return payment.mark_failed(
                f"Confirmation wait failed (tx may still be mining): "
                f"{type(e).__name__}: {e}",
                now,
                tx_hash=tx_hash,
            )

        # --- 4. Interpret the receipt ----------------------------------
        if not receipt.success:
            return payment.mark_failed(
                "Transaction reverted on-chain",
                now,
                tx_hash=receipt.tx_hash,
            )

        return payment.mark_confirmed(
            tx_hash=receipt.tx_hash,
            block_number=receipt.block_number,
            now=now,
        )
