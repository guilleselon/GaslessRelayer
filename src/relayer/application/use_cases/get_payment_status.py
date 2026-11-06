"""Get payment status use case (read-only)."""

from __future__ import annotations

from relayer.application.dto import PaymentStatusOutput
from relayer.application.exceptions import PaymentNotFoundError
from relayer.application.unit_of_work import UnitOfWorkFactory


class GetPaymentStatusUseCase:
    """Return the current status of a payment by id."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, request_id: int) -> PaymentStatusOutput:
        with self._uow_factory() as uow:
            payment = uow.payments.get_by_id(request_id)

        if payment is None:
            raise PaymentNotFoundError(f"Payment {request_id} not found")

        return PaymentStatusOutput(
            request_id=payment.id if payment.id is not None else request_id,
            status=payment.status.value,
            tx_hash=payment.tx_hash,
            block_number=payment.block_number,
            error=payment.error,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
