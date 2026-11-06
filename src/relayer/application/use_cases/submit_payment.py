"""Submit payment use case (the "Bouncer" in the architecture).

Validates an incoming authorization, enforces policy, and persists it
for execution. Idempotent on (from_address, nonce).
"""

from __future__ import annotations

from relayer.application.dto import SubmitPaymentInput, SubmitPaymentOutput
from relayer.application.unit_of_work import UnitOfWorkFactory
from relayer.domain.entities import Authorization, PaymentRequest
from relayer.domain.exceptions import (
    DuplicatePaymentError,
    InvalidNonceError,
    InvalidSignatureError,
)
from relayer.domain.ports import Clock
from relayer.domain.services import AuthorizationValidator
from relayer.domain.value_objects import (
    Address,
    Amount,
    Nonce,
    Signature,
)


class SubmitPaymentUseCase:
    """Validate an authorization and enqueue it for execution."""

    def __init__(
        self,
        validator: AuthorizationValidator,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        token_decimals: int,
    ) -> None:
        self._validator = validator
        self._uow_factory = uow_factory
        self._clock = clock
        self._decimals = token_decimals

    def execute(self, input_dto: SubmitPaymentInput) -> SubmitPaymentOutput:
        # 1. Structural parsing (fails fast, before opening any transaction)
        authorization = self._build_authorization(input_dto)

        # 2. Domain validation (policy + signature)
        now = self._clock.now()
        self._validator.validate(authorization, now)

        # 3. Persist (idempotent via UNIQUE constraint)
        payment = PaymentRequest.create(authorization, now)

        try:
            with self._uow_factory() as uow:
                saved = uow.payments.save_new(payment)
                uow.commit()
            return SubmitPaymentOutput(
                request_id=saved.id,
                status=saved.status.value,
                is_duplicate=False,
            )
        except DuplicatePaymentError:
            # Race with another request for the same (from, nonce): fetch it
            with self._uow_factory() as uow:
                existing = uow.payments.get_by_from_and_nonce(
                    authorization.from_address, authorization.nonce
                )
            if existing is None or existing.id is None:
                raise  # invariant: DuplicatePaymentError implies a persisted row
            return SubmitPaymentOutput(
                request_id=existing.id,
                status=existing.status.value,
                is_duplicate=True,
            )

    def _build_authorization(self, dto: SubmitPaymentInput) -> Authorization:
        try:
            r_bytes = bytes.fromhex(dto.r.removeprefix("0x").removeprefix("0X"))
            s_bytes = bytes.fromhex(dto.s.removeprefix("0x").removeprefix("0X"))
        except ValueError as e:
            raise InvalidSignatureError(f"Malformed signature hex: {e}") from e

        try:
            value_raw = int(dto.value_raw)
        except (TypeError, ValueError) as e:
            raise InvalidSignatureError(
                f"value_raw is not a valid integer string: {dto.value_raw}"
            ) from e

        return Authorization(
            from_address=Address(dto.from_address),
            to_address=Address(dto.to_address),
            value=Amount(raw=value_raw, decimals=self._decimals),
            valid_after=dto.valid_after,
            valid_before=dto.valid_before,
            nonce=Nonce.from_hex(dto.nonce),
            signature=Signature(v=dto.v, r=r_bytes, s=s_bytes),
        )
