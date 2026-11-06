"""Smoke test for Layer 6: infrastructure adapters.

Uses real implementations:
  - SystemClock (real time)
  - Eip712SignatureVerifier (real eth_account sign + recover)
  - SQLitePaymentRepository + SQLiteUnitOfWork (real temp DB)
  - Composition root wiring

Skips the on-chain gateway (requires RPC access; tested separately).
"""

import os
import tempfile
import time

from eth_account import Account
from eth_account.messages import encode_typed_data

from relayer.application.dto import SubmitPaymentInput
from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.exceptions import (
    DuplicatePaymentError,
    InvalidStateTransitionError,
)
from relayer.domain.value_objects import (
    Address, Amount, Nonce, Policy, Signature,
)
from relayer.infrastructure.clock import SystemClock
from relayer.infrastructure.persistence import (
    init_schema, make_sqlite_uow_factory,
)
from relayer.infrastructure.signature_verifier import Eip712SignatureVerifier


# =====================================================================
# Part 1: SystemClock
# =====================================================================
clock = SystemClock()
t1 = clock.now()
time.sleep(0.01)
t2 = clock.now()
assert isinstance(t1, int) and isinstance(t2, int)
assert t2 >= t1
print("✅ SystemClock OK")


# =====================================================================
# Part 2: Eip712SignatureVerifier (real sign + recover)
# =====================================================================
CHAIN_ID = 11155111
CONTRACT = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
TOKEN_NAME = "USDC"
TOKEN_VERSION = "2"

verifier = Eip712SignatureVerifier(
    chain_id=CHAIN_ID,
    verifying_contract=CONTRACT,
    token_name=TOKEN_NAME,
    token_version=TOKEN_VERSION,
)

# Generate a fresh EOA and sign a real authorization
account = Account.create()
from_addr = Address(account.address)
to_addr = Address("0x1234567890123456789012345678901234567890")
amount = Amount.from_human("1.5", 6)
nonce = Nonce.from_hex("0x" + "aa" * 32)
valid_after = 1000
valid_before = 2000

domain = {
    "name": TOKEN_NAME,
    "version": TOKEN_VERSION,
    "chainId": CHAIN_ID,
    "verifyingContract": CONTRACT,
}
types = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}
message = {
    "from": account.address,
    "to": to_addr.value,
    "value": amount.raw,
    "validAfter": valid_after,
    "validBefore": valid_before,
    "nonce": nonce.value,
}
signed = Account.sign_typed_data(
    private_key=account.key,
    domain_data=domain,
    message_types=types,
    message_data=message,
)
sig = Signature.from_bytes(signed.signature)

auth = Authorization(
    from_address=from_addr,
    to_address=to_addr,
    value=amount,
    valid_after=valid_after,
    valid_before=valid_before,
    nonce=nonce,
    signature=sig,
)

recovered = verifier.recover_signer(auth)
assert recovered == from_addr, f"recovered {recovered} != {from_addr}"

# A tampered message recovers to a different address
wrong_auth = Authorization(
    from_address=from_addr,
    to_address=to_addr,
    value=Amount.from_human("2.5", 6),  # different value
    valid_after=valid_after,
    valid_before=valid_before,
    nonce=nonce,
    signature=sig,
)
assert verifier.recover_signer(wrong_auth) != from_addr

# Malformed signature -> zero address
bad_sig = Signature(v=27, r=b"\x00" * 32, s=b"\x00" * 32)
bad_auth = Authorization(
    from_address=from_addr,
    to_address=to_addr,
    value=amount,
    valid_after=valid_after,
    valid_before=valid_before,
    nonce=nonce,
    signature=bad_sig,
)
assert verifier.recover_signer(bad_auth).is_zero

print("✅ Eip712SignatureVerifier OK")


# =====================================================================
# Part 3: SQLite persistence
# =====================================================================
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
try:
    init_schema(db_path)
    uow_factory = make_sqlite_uow_factory(db_path)

    payment = PaymentRequest.create(auth, now=1500)

    # 3.1 save_new assigns an id and persists
    with uow_factory() as uow:
        saved = uow.payments.save_new(payment)
        uow.commit()
    assert saved.id is not None and saved.id > 0
    saved_id = saved.id

    # 3.2 get_by_id reads it back correctly
    with uow_factory() as uow:
        loaded = uow.payments.get_by_id(saved_id)
    assert loaded is not None
    assert loaded.authorization.from_address == from_addr
    assert loaded.authorization.to_address == to_addr
    assert loaded.authorization.value.raw == amount.raw
    assert loaded.authorization.value.decimals == amount.decimals
    assert loaded.authorization.nonce == nonce
    assert loaded.authorization.signature.v == sig.v
    assert loaded.status == PaymentStatus.PENDING

    # 3.3 get_by_from_and_nonce finds it
    with uow_factory() as uow:
        found = uow.payments.get_by_from_and_nonce(from_addr, nonce)
    assert found is not None and found.id == saved_id

    # 3.4 Duplicate on (from, nonce) raises DuplicatePaymentError
    try:
        with uow_factory() as uow:
            uow.payments.save_new(payment)
            uow.commit()
    except DuplicatePaymentError:
        pass
    else:
        raise AssertionError("DuplicatePaymentError not raised")

    # 3.5 Rollback discards writes
    rollback_auth = Authorization(
        from_address=from_addr,
        to_address=to_addr,
        value=amount,
        valid_after=valid_after,
        valid_before=valid_before,
        nonce=Nonce.from_hex("0x" + "bb" * 32),
        signature=sig,
    )
    rollback_payment = PaymentRequest.create(rollback_auth, now=1500)
    try:
        with uow_factory() as uow:
            uow.payments.save_new(rollback_payment)
            # no commit -> rollback on __exit__
    finally:
        pass
    with uow_factory() as uow:
        gone = uow.payments.get_by_from_and_nonce(
            rollback_auth.from_address, rollback_auth.nonce
        )
    assert gone is None, "rollback did not revert the insert"

    # 3.6 claim_pending returns PROCESSING and is idempotent per worker
    with uow_factory() as uow:
        claimed = uow.payments.claim_pending(limit=10, now=1600)
        uow.commit()
    assert len(claimed) == 1
    assert claimed[0].status == PaymentStatus.PROCESSING
    assert claimed[0].id == saved_id

    # 3.7 claim_pending returns empty the second time
    with uow_factory() as uow:
        again = uow.payments.claim_pending(limit=10, now=1700)
        uow.commit()
    assert again == []

    # 3.8 save persists transitions
    confirmed = claimed[0].mark_confirmed("0xabc", 99, now=1800)
    with uow_factory() as uow:
        uow.payments.save(confirmed)
        uow.commit()
    with uow_factory() as uow:
        reloaded = uow.payments.get_by_id(saved_id)
    assert reloaded is not None
    assert reloaded.status == PaymentStatus.CONFIRMED
    assert reloaded.tx_hash == "0xabc"
    assert reloaded.block_number == 99

    # 3.9 save with non-existent id raises InvalidStateTransitionError
    ghost = PaymentRequest(
        id=9999,
        authorization=auth,
        status=PaymentStatus.PENDING,
        tx_hash=None,
        block_number=None,
        error=None,
        created_at=1500,
        updated_at=1500,
    )
    try:
        with uow_factory() as uow:
            uow.payments.save(ghost)
            uow.commit()
    except InvalidStateTransitionError:
        pass
    else:
        raise AssertionError("InvalidStateTransitionError not raised")

finally:
    os.unlink(db_path)

print("✅ SQLite repository + UnitOfWork OK")


# =====================================================================
# Part 4: Composition root (without touching the network)
# =====================================================================
# We only verify the wiring compiles; ChainGateway requires RPC.
# For a full end-to-end test, run scripts/integration_sepolia.py.
from relayer.infrastructure.composition import Container, Config  # noqa: F401

policy = Policy(
    max_value=Amount.from_human("10", 6),
    max_validity_window_seconds=7200,
    min_remaining_validity_seconds=60,
)
_ = Config(
    rpc_url="http://localhost:0",  # not used in this smoke
    chain_id=CHAIN_ID,
    usdc_address=CONTRACT,
    usdc_name=TOKEN_NAME,
    usdc_version=TOKEN_VERSION,
    token_decimals=6,
    relayer_private_key="0x" + "11" * 32,
    db_path=":memory:",
    policy=policy,
)
# We don't call build_container() because it would try to connect to RPC.
print("✅ Composition root types import cleanly")

print("\n🎉 Layer 6 (infrastructure) OK")
print("   ChainGateway end-to-end requires scripts/integration_sepolia.py")
