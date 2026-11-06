"""Execute pending payments use case (the "Engine" orchestration).

Claims a batch of PENDING payments atomically, drives the domain
PaymentExecutor on each, and persists the terminal results.

NOTE ON RECONCILIATION
======================
This use case does not handle the case where the process crashes
between the claim commit and the final save. Such payments remain
stuck in PROCESSING forever. A separate reconciliation job (not part
of this MVP) must periodically scan for PROCESSING rows older than
a threshold, query the chain to determine the on-chain truth, and
fix the persisted state accordingly.
"""

from __future__ import annotations

from relayer.application.dto import (
    BatchExecutionOutput,
    PaymentExecutionResult,
)
from relayer.application.unit_of_work import UnitOfWorkFactory
from relayer.domain.entities import PaymentRequest
from relayer.domain.ports import Clock
from relayer.domain.services import PaymentExecutor


class ExecutePendingPaymentsUseCase:
    """Claim a batch of pending payments and execute them."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        executor: PaymentExecutor,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._executor = executor

    def run_batch(self, batch_size: int) -> BatchExecutionOutput:
        if batch_size <= 0:
            return BatchExecutionOutput(
                processed=0, confirmed=0, failed=0, results=()
            )

        # --- Phase 1: atomic claim (its own transaction) -----------------
        with self._uow_factory() as uow:
            claimed = uow.payments.claim_pending(batch_size, self._clock.now())
            uow.commit()

        if not claimed:
            return BatchExecutionOutput(
                processed=0, confirmed=0, failed=0, results=()
            )

        # --- Phase 2: execute each, persisting independently -------------
        results: list[PaymentExecutionResult] = []
        for payment in claimed:
            result_entity = self._executor.execute(payment, self._clock.now())

            # Persist (isolated transaction per payment)
            with self._uow_factory() as uow:
                uow.payments.save(result_entity)
                uow.commit()

            results.append(self._to_result(result_entity))

        confirmed = sum(1 for r in results if r.status == "confirmed")
        failed = sum(1 for r in results if r.status == "failed")

        return BatchExecutionOutput(
            processed=len(results),
            confirmed=confirmed,
            failed=failed,
            results=tuple(results),
        )

    @staticmethod
    def _to_result(payment: PaymentRequest) -> PaymentExecutionResult:
        return PaymentExecutionResult(
            request_id=payment.id if payment.id is not None else -1,
            status=payment.status.value,
            tx_hash=payment.tx_hash,
            error=payment.error,
        )
