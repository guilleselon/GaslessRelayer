"""SQLite implementation of PaymentRepository.

Bound to a single connection owned by the UnitOfWork. Not thread-safe
by itself; thread safety comes from giving each UnitOfWork its own
connection.
"""

from __future__ import annotations

import sqlite3

from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.exceptions import (
    DuplicatePaymentError,
    InvalidStateTransitionError,
)
from relayer.domain.value_objects import (
    Address,
    Amount,
    Nonce,
    Signature,
)


class SQLitePaymentRepository:
    """PaymentRepository bound to one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- Writes ----------------------------------------------------------

    def save_new(self, payment: PaymentRequest) -> PaymentRequest:
        auth = payment.authorization
        try:
            cur = self._conn.execute(
                """INSERT INTO payment_requests
                   (from_addr, to_addr, value_raw, decimals,
                    valid_after, valid_before, nonce_hex,
                    v, r_hex, s_hex, status,
                    tx_hash, block_number, error,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    auth.from_address.value,
                    auth.to_address.value,
                    str(auth.value.raw),
                    auth.value.decimals,
                    auth.valid_after,
                    auth.valid_before,
                    auth.nonce.to_hex(),
                    auth.signature.v,
                    "0x" + auth.signature.r.hex(),
                    "0x" + auth.signature.s.hex(),
                    payment.status.value,
                    payment.tx_hash,
                    payment.block_number,
                    payment.error,
                    payment.created_at,
                    payment.updated_at,
                ),
            )
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise DuplicatePaymentError(
                    f"Payment already exists for "
                    f"(from={auth.from_address}, nonce={auth.nonce})"
                ) from e
            raise

        return PaymentRequest(
            id=cur.lastrowid,
            authorization=auth,
            status=payment.status,
            tx_hash=payment.tx_hash,
            block_number=payment.block_number,
            error=payment.error,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    def save(self, payment: PaymentRequest) -> None:
        if payment.id is None:
            raise InvalidStateTransitionError(
                "Cannot save a payment without an id"
            )
        cur = self._conn.execute(
            """UPDATE payment_requests
               SET status = ?, tx_hash = ?, block_number = ?, error = ?,
                   updated_at = ?
               WHERE id = ?""",
            (
                payment.status.value,
                payment.tx_hash,
                payment.block_number,
                payment.error,
                payment.updated_at,
                payment.id,
            ),
        )
        if cur.rowcount == 0:
            raise InvalidStateTransitionError(
                f"Payment {payment.id} does not exist"
            )

    # --- Reads -----------------------------------------------------------

    def get_by_id(self, payment_id: int) -> PaymentRequest | None:
        row = self._conn.execute(
            "SELECT * FROM payment_requests WHERE id = ?", (payment_id,)
        ).fetchone()
        return self._row_to_payment(row) if row else None

    def get_by_from_and_nonce(
        self, from_address: Address, nonce: Nonce
    ) -> PaymentRequest | None:
        row = self._conn.execute(
            "SELECT * FROM payment_requests "
            "WHERE from_addr = ? AND nonce_hex = ?",
            (from_address.value, nonce.to_hex()),
        ).fetchone()
        return self._row_to_payment(row) if row else None

    def claim_pending(self, limit: int, now: int) -> list[PaymentRequest]:
        rows = self._conn.execute(
            "SELECT id FROM payment_requests "
            "WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return []

        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE payment_requests "
            f"SET status = 'processing', updated_at = ? "
            f"WHERE id IN ({placeholders})",
            (now, *ids),
        )
        updated = self._conn.execute(
            f"SELECT * FROM payment_requests WHERE id IN ({placeholders}) "
            f"ORDER BY id ASC",
            ids,
        ).fetchall()
        return [self._row_to_payment(r) for r in updated]

    # --- Mapping ---------------------------------------------------------

    @staticmethod
    def _row_to_payment(row: sqlite3.Row) -> PaymentRequest:
        auth = Authorization(
            from_address=Address(row["from_addr"]),
            to_address=Address(row["to_addr"]),
            value=Amount(raw=int(row["value_raw"]), decimals=row["decimals"]),
            valid_after=row["valid_after"],
            valid_before=row["valid_before"],
            nonce=Nonce.from_hex(row["nonce_hex"]),
            signature=Signature(
                v=row["v"],
                r=bytes.fromhex(row["r_hex"].removeprefix("0x")),
                s=bytes.fromhex(row["s_hex"].removeprefix("0x")),
            ),
        )
        return PaymentRequest(
            id=row["id"],
            authorization=auth,
            status=PaymentStatus(row["status"]),
            tx_hash=row["tx_hash"],
            block_number=row["block_number"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
