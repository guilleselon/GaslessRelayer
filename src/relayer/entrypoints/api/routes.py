"""HTTP route handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from relayer.application.dto import PaymentStatusOutput, SubmitPaymentOutput
from relayer.application.use_cases import (
    GetPaymentStatusUseCase,
    SubmitPaymentUseCase,
)
from relayer.entrypoints.api.dependencies import get_container
from relayer.entrypoints.api.schemas import (
    HealthResponse,
    PaymentStatusResponse,
    SubmitPaymentRequest,
    SubmitPaymentResponse,
)
from relayer.infrastructure.composition import Container


router = APIRouter()


@router.post(
    "/pay",
    response_model=SubmitPaymentResponse,
    status_code=201,
    summary="Submit an EIP-3009 authorization for sponsored execution",
)
def submit_payment(
    payload: SubmitPaymentRequest,
    container: Container = Depends(get_container),
) -> SubmitPaymentResponse:
    use_case: SubmitPaymentUseCase = container.submit_payment
    output: SubmitPaymentOutput = use_case.execute(payload.to_dto())
    return SubmitPaymentResponse.from_output(output)


@router.get(
    "/status/{request_id}",
    response_model=PaymentStatusResponse,
    summary="Get the status of a payment",
)
def get_payment_status(
    request_id: int = Path(..., ge=1),
    container: Container = Depends(get_container),
) -> PaymentStatusResponse:
    use_case: GetPaymentStatusUseCase = container.get_payment_status
    output: PaymentStatusOutput = use_case.execute(request_id)
    return PaymentStatusResponse.from_output(output)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and readiness probe",
)
def health(container: Container = Depends(get_container)) -> HealthResponse:
    details: dict[str, str] = {}
    db_ok = False
    try:
        # A lightweight query to verify the DB is reachable
        with container.uow_factory() as uow:
            uow.payments.get_by_id(-1)
        db_ok = True
        details["db"] = "ok"
    except Exception as e:
        details["db"] = f"error: {type(e).__name__}: {e}"

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_ok=db_ok,
        details=details,
    )
