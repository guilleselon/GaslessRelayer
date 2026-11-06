"""Smoke test for Layer 4: authorization_validator + payment_executor."""

from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.exceptions import (
    AuthorizationExpiredError,
    AuthorizationNotYetValidError,
    InvalidSignatureError,
    InvalidStateTransitionError,
    PolicyViolationError,
)
from relayer.domain.services import AuthorizationValidator, PaymentExecutor
from relayer.domain.value_objects import (
    Address, Amount, Nonce, Policy, Signature, TxReceipt,
)


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"{exc_type.__name__} not raised")


# --- Shared fixtures --------------------------------------------------
FROM = Address("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
TO = Address("0x1234567890123456789012345678901234567890")
TO_OTHER = Address("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
VALID_AFTER = 1000
VALID_BEFORE = 2000
NOW = 1500

AMOUNT = Amount.from_human("1.5", 6)


def build_auth(
    to: Address = TO,
    value: Amount = AMOUNT,
    valid_after: int = VALID_AFTER,
    valid_before: int = VALID_BEFORE,
) -> Authorization:
    return Authorization(
        from_address=FROM,
        to_address=to,
        value=value,
        valid_after=valid_after,
        valid_before=valid_before,
        nonce=Nonce.from_hex("0x" + "aa" * 32),
        signature=Signature.from_bytes(b"\x11" * 32 + b"\x22" * 32 + b"\x1b"),
    )


def build_policy(allowed=None) -> Policy:
    return Policy(
        max_value=Amount.from_human("10", 6),
        max_validity_window_seconds=7200,
        min_remaining_validity_seconds=60,
        allowed_destinations=allowed,
    )


# =====================================================================
# SignatureVerifier fakes
# =====================================================================
class GoodVerifier:
    def recover_signer(self, authorization: Authorization) -> Address:
        return authorization.from_address


class WrongSignerVerifier:
    def recover_signer(self, authorization: Authorization) -> Address:
        return TO_OTHER


class ZeroSignerVerifier:
    def recover_signer(self, authorization: Authorization) -> Address:
        return Address.zero()


# =====================================================================
# PART 1: AuthorizationValidator
# =====================================================================
validator = AuthorizationValidator(GoodVerifier(), build_policy())

# 1. Happy path
validator.validate(build_auth(), NOW)

# 2. Expired
assert_raises(
    AuthorizationExpiredError,
    validator.validate, build_auth(valid_before=NOW - 1), NOW,
)

# 3. Not yet valid
assert_raises(
    AuthorizationNotYetValidError,
    validator.validate, build_auth(valid_after=NOW + 1), NOW,
)

# 4. Window too large (policy: 7200s; here 8000s)
assert_raises(
    PolicyViolationError,
    validator.validate, build_auth(valid_after=0, valid_before=8000), NOW,
)

# 5. Insufficient remaining validity (policy: 60s; here 30s)
assert_raises(
    PolicyViolationError,
    validator.validate, build_auth(valid_after=1470, valid_before=1530), NOW,
)

# 6. Value exceeds policy maximum (policy: 10 USDC; here 20)
assert_raises(
    PolicyViolationError,
    validator.validate,
    build_auth(value=Amount.from_human("20", 6)), NOW,
)

# 7. Destination not in allowlist
restricted = AuthorizationValidator(
    GoodVerifier(), build_policy(allowed=frozenset({TO}))
)
assert_raises(
    PolicyViolationError, restricted.validate, build_auth(to=TO_OTHER), NOW,
)
# ... and the allowed destination still passes
restricted.validate(build_auth(to=TO), NOW)

# 8. Signature does not match from_address
assert_raises(
    InvalidSignatureError,
    AuthorizationValidator(WrongSignerVerifier(), build_policy()).validate,
    build_auth(), NOW,
)

# 9. Signature recovers to zero
assert_raises(
    InvalidSignatureError,
    AuthorizationValidator(ZeroSignerVerifier(), build_policy()).validate,
    build_auth(), NOW,
)

print("✅ AuthorizationValidator OK")


# =====================================================================
# PART 2: PaymentExecutor
# =====================================================================
class FakeChain:
    def __init__(
        self,
        nonce_used: bool = False,
        submit_raises: Exception | None = None,
        wait_raises: Exception | None = None,
        receipt: TxReceipt | None = None,
    ):
        self.nonce_used = nonce_used
        self.submit_raises = submit_raises
        self.wait_raises = wait_raises
        self.receipt = receipt or TxReceipt(
            tx_hash="0xdead", block_number=42, success=True
        )
        self.submitted: list[Authorization] = []

    def is_nonce_used(self, from_address, nonce) -> bool:
        return self.nonce_used

    def transfer_with_authorization(self, authorization) -> str:
        if self.submit_raises:
            raise self.submit_raises
        self.submitted.append(authorization)
        return self.receipt.tx_hash

    def wait_for_confirmation(self, tx_hash: str) -> TxReceipt:
        if self.wait_raises:
            raise self.wait_raises
        return self.receipt


def processing_payment() -> PaymentRequest:
    pr = PaymentRequest.create(build_auth(), now=1000)
    pr = pr.mark_processing(now=1500)
    assert pr.status == PaymentStatus.PROCESSING
    return pr


# 1. Happy path
chain = FakeChain()
result = PaymentExecutor(chain).execute(processing_payment(), NOW)
assert result.status == PaymentStatus.CONFIRMED
assert result.tx_hash == "0xdead" and result.block_number == 42
assert chain.submitted == [processing_payment().authorization]

# 2. Nonce already consumed
chain = FakeChain(nonce_used=True)
result = PaymentExecutor(chain).execute(processing_payment(), NOW)
assert result.status == PaymentStatus.FAILED
assert "nonce already consumed" in result.error.lower()
assert chain.submitted == []

# 3. Submission raises
chain = FakeChain(submit_raises=ConnectionError("RPC down"))
result = PaymentExecutor(chain).execute(processing_payment(), NOW)
assert result.status == PaymentStatus.FAILED
assert "submission failed" in result.error.lower()
assert result.tx_hash is None

# 4. Confirmation raises — tx_hash preserved
chain = FakeChain(wait_raises=TimeoutError("no receipt after 180s"))
result = PaymentExecutor(chain).execute(processing_payment(), NOW)
assert result.status == PaymentStatus.FAILED
assert "confirmation wait failed" in result.error.lower()
assert result.tx_hash == "0xdead"

# 5. Receipt indicates revert
chain = FakeChain(receipt=TxReceipt(tx_hash="0xdead", block_number=42, success=False))
result = PaymentExecutor(chain).execute(processing_payment(), NOW)
assert result.status == PaymentStatus.FAILED
assert "reverted" in result.error.lower()
assert result.tx_hash == "0xdead"

# 6. Rejects non-PROCESSING input
pending = PaymentRequest.create(build_auth(), now=1000)
assert_raises(
    InvalidStateTransitionError,
    PaymentExecutor(FakeChain()).execute, pending, NOW,
)

print("✅ PaymentExecutor OK")
print("\n🎉 Layer 4 (domain services) OK")
