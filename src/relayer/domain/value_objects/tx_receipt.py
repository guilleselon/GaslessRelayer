"""Transaction receipt value object.

A minimal, infrastructure-agnostic representation of a confirmed
on-chain transaction. The chain adapter is responsible for extracting
these three fields from the RPC response.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.domain.exceptions import InvalidTxReceiptError


@dataclass(frozen=True, slots=True)
class TxReceipt:
    """The outcome of a transaction that has been mined."""

    tx_hash: str
    block_number: int
    success: bool

    def __post_init__(self) -> None:
        if not isinstance(self.tx_hash, str) or not self.tx_hash:
            raise InvalidTxReceiptError("tx_hash must be a non-empty string")
        if not isinstance(self.block_number, int) or isinstance(self.block_number, bool):
            raise InvalidTxReceiptError("block_number must be an int")
        if self.block_number < 0:
            raise InvalidTxReceiptError("block_number cannot be negative")
        if not isinstance(self.success, bool):
            raise InvalidTxReceiptError("success must be a bool")
