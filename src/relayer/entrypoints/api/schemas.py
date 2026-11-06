"""HTTP schemas. Thin Pydantic wrappers around application DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from relayer.application.dto import (
    PaymentStatusOutput,
    SubmitPaymentInput,
    SubmitPaymentOutput,
)


class SubmitPaymentRequest(BaseModel):
    """Incoming payment authorization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_address: str = Field(..., alias="from", min_length=42, max_length=42)
    to_address: str = Field(..., alias="to", min_length=42, max_length=42)
    value_raw: str = Field(..., pattern=r"^\d+$")
    valid_after: int = Field(..., ge=0)
    valid_before: int = Field(..., ge=0)
    nonce: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")
    v: int = Field(..., ge=0, le=28)
    r: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")
    s: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")

    def to_dto(self) -> SubmitPaymentInput:
        return SubmitPaymentInput(
            from_address=self.from_address,
            to_address=self.to_address,
            value_raw=self.value_raw,
            valid_after=self.valid_after,
            valid_before=self.valid_before,
            nonce=self.nonce,
            v=self.v,
            r=self.r,
            s=self.s,
        )


class SubmitPaymentResponse(BaseModel):
    request_id: int
    status: str
    is_duplicate: bool

    @classmethod
    def from_output(cls, out: SubmitPaymentOutput) -> "SubmitPaymentResponse":
        return cls(
            request_id=out.request_id,
            status=out.status,
            is_duplicate=out.is_duplicate,
        )


class PaymentStatusResponse(BaseModel):
    request_id: int
    status: str
    tx_hash: str | None
    block_number: int | None
    error: str | None
    created_at: int
    updated_at: int

    @classmethod
    def from_output(cls, out: PaymentStatusOutput) -> "PaymentStatusResponse":
        return cls(
            request_id=out.request_id,
            status=out.status,
            tx_hash=out.tx_hash,
            block_number=out.block_number,
            error=out.error,
            created_at=out.created_at,
            updated_at=out.updated_at,
        )


class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    details: dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    message: str
