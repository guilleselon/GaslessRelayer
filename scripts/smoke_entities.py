from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.exceptions import (
    InvalidAuthorizationError,
    InvalidSignatureError,
    InvalidStateTransitionError,
)
from relayer.domain.value_objects import Address, Amount, Nonce, Signature


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"{exc_type.__name__} not raised")


# --- Signature --------------------------------------------------------
raw = b"\x11" * 32 + b"\x22" * 32 + b"\x1b"  # r || s || v=27
sig = Signature.from_bytes(raw)
assert sig.v == 27 and sig.r == b"\x11" * 32 and sig.s == b"\x22" * 32
assert sig.to_bytes() == raw

# v normalization: 0/1 -> 27/28
assert Signature(v=0, r=b"\x11" * 32, s=b"\x22" * 32).v == 27
assert Signature(v=1, r=b"\x11" * 32, s=b"\x22" * 32).v == 28

# Invalid signatures
assert_raises(InvalidSignatureError, Signature, 29, b"\x11" * 32, b"\x22" * 32)
assert_raises(InvalidSignatureError, Signature, 27, b"\x11" * 31, b"\x22" * 32)
assert_raises(InvalidSignatureError, Signature.from_bytes, b"short")


# --- Authorization ----------------------------------------------------
usdc_from = Address("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
usdc_to = Address("0x1234567890123456789012345678901234567890")
amount = Amount.from_human("1.5", 6)
nonce = Nonce.from_hex("0x" + "aa" * 32)

auth = Authorization(
    from_address=usdc_from,
    to_address=usdc_to,
    value=amount,
    valid_after=1000,
    valid_before=2000,
    nonce=nonce,
    signature=sig,
)
assert auth.is_valid_at(1500)
assert not auth.is_valid_at(1000)      # boundary: == valid_after -> invalid
assert not auth.is_valid_at(2000)      # boundary: == valid_before -> expired
assert auth.is_expired(2000)
assert auth.is_expired(3000)
assert auth.is_not_yet_valid(1000)
assert auth.is_not_yet_valid(500)

# Invalid authorizations
assert_raises(
    InvalidAuthorizationError,
    Authorization,
    Address.zero(), usdc_to, amount, 1000, 2000, nonce, sig,
)
assert_raises(
    InvalidAuthorizationError,
    Authorization,
    usdc_from, usdc_from, amount, 1000, 2000, nonce, sig,
)
assert_raises(
    InvalidAuthorizationError,
    Authorization,
    usdc_from, usdc_to, Amount.zero(6), 1000, 2000, nonce, sig,
)
assert_raises(
    InvalidAuthorizationError,
    Authorization,
    usdc_from, usdc_to, amount, 2000, 1000, nonce, sig,
)


# --- PaymentRequest: creation -----------------------------------------
now = 1500
pr = PaymentRequest.create(auth, now=now)
assert pr.id is None
assert pr.status == PaymentStatus.PENDING
assert pr.tx_hash is None and pr.error is None
assert not pr.is_terminal


# --- PaymentRequest: PENDING -> PROCESSING ----------------------------
pr2 = pr.mark_processing(now + 1)
assert pr2.status == PaymentStatus.PROCESSING
assert pr2.updated_at == now + 1
assert pr.status == PaymentStatus.PENDING        # original untouched
assert not pr2.is_terminal


# --- PaymentRequest: PROCESSING -> CONFIRMED --------------------------
pr3 = pr2.mark_confirmed(tx_hash="0xabc", block_number=12345, now=now + 2)
assert pr3.status == PaymentStatus.CONFIRMED
assert pr3.tx_hash == "0xabc" and pr3.block_number == 12345
assert pr3.is_terminal


# --- PaymentRequest: PROCESSING -> FAILED -----------------------------
pr4 = pr2.mark_failed("reverted on-chain", now=now + 3, tx_hash="0xdef")
assert pr4.status == PaymentStatus.FAILED
assert pr4.error == "reverted on-chain" and pr4.tx_hash == "0xdef"
assert pr4.is_terminal


# --- PaymentRequest: invalid transitions ------------------------------
assert_raises(InvalidStateTransitionError, pr.mark_confirmed, "0xabc", 1, now + 4)
assert_raises(InvalidStateTransitionError, pr3.mark_processing, now + 5)
assert_raises(InvalidStateTransitionError, pr3.mark_failed, "err", now + 6)
assert_raises(InvalidStateTransitionError, pr4.mark_processing, now + 7)

# Invalid arguments to transitions
assert_raises(InvalidStateTransitionError, pr2.mark_confirmed, "", 1, now + 8)
assert_raises(InvalidStateTransitionError, pr2.mark_confirmed, "0xabc", -1, now + 9)
assert_raises(InvalidStateTransitionError, pr2.mark_failed, "", now + 10)


print("✅ Layer 2 (entities) OK")
