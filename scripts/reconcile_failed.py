"""Reconcile payments marked as FAILED that actually confirmed on-chain.

Scans every row with status='failed' AND tx_hash IS NOT NULL,
queries the chain for the real receipt, and updates the row.
"""

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web3 import Web3
from relayer.config import Settings


def main() -> None:
    settings = Settings.from_env()
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url))

    print(f"RPC: {settings.rpc_url}")
    print(f"DB:  {settings.db_path}\n")

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, tx_hash, status FROM payment_requests "
        "WHERE status = 'failed' AND tx_hash IS NOT NULL"
    ).fetchall()

    if not rows:
        print("No failed payments with a tx_hash. Nothing to reconcile.")
        return

    print(f"Found {len(rows)} candidate(s):\n")

    fixed = 0
    reverted = 0
    missing = 0

    for row in rows:
        req_id = row["id"]
        tx_hash = row["tx_hash"]
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            print(f"  #{req_id}: cannot fetch receipt ({e}); skipping")
            missing += 1
            continue

        if receipt is None:
            print(f"  #{req_id}: tx not mined yet")
            missing += 1
            continue

        if receipt["status"] == 1:
            conn.execute(
                "UPDATE payment_requests SET status='confirmed', "
                "block_number=?, error=NULL, "
                "updated_at=strftime('%s','now') WHERE id=?",
                (receipt["blockNumber"], req_id),
            )
            print(
                f"  #{req_id}: ✅ CONFIRMED (block {receipt['blockNumber']}) "
                f"-> updated"
            )
            fixed += 1
        else:
            print(f"  #{req_id}: ❌ reverted on-chain (status correct)")
            reverted += 1

    conn.commit()
    conn.close()

    print()
    print(f"Confirmed: {fixed} | Reverted: {reverted} | Pending/unknown: {missing}")


if __name__ == "__main__":
    main()
