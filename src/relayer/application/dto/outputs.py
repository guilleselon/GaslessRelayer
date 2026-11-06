"""Output DTOs: primitives ready for external serialization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubmitPaymentOutput:
    request_id: int
    status: str
    is_duplicate: bool


@dataclass(frozen=True, slots=True)
class PaymentStatusOutput:
    request_id: int
    status: str
    tx_hash: str | None
    block_number: int | None
    error: str | None
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class PaymentExecutionResult:
    request_id: int
    status: str
    tx_hash: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class BatchExecutionOutput:
    processed: int
    confirmed: int
    failed: int
    results: tuple[PaymentExecutionResult, ...]
