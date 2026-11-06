"""SQLite schema for the payment requests table.

The UNIQUE(from_addr, nonce_hex) constraint enforces idempotency
at the storage engine level, not in Python. This is what makes the
DuplicatePaymentError guarantee real under concurrency.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS payment_requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_addr      TEXT    NOT NULL,
    to_addr        TEXT    NOT NULL,
    value_raw      TEXT    NOT NULL,
    decimals       INTEGER NOT NULL,
    valid_after    INTEGER NOT NULL,
    valid_before   INTEGER NOT NULL,
    nonce_hex      TEXT    NOT NULL,
    v              INTEGER NOT NULL,
    r_hex          TEXT    NOT NULL,
    s_hex          TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending',
    tx_hash        TEXT,
    block_number   INTEGER,
    error          TEXT,
    created_at     INTEGER NOT NULL,
    updated_at     INTEGER NOT NULL,
    UNIQUE(from_addr, nonce_hex)
);

CREATE INDEX IF NOT EXISTS idx_payment_status
    ON payment_requests(status);
CREATE INDEX IF NOT EXISTS idx_payment_created
    ON payment_requests(created_at);
"""
