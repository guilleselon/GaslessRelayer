"""Smoke test for Layer 5: application layer (use cases + UoW)."""

from relayer.application import PaymentNotFoundError
from relayer.application.dto import SubmitPaymentInput
from relayer.application.use_cases import (
    ExecutePendingPaymentsUseCase,
    GetPaymentStatusUseCase,
    SubmitPaymentUseCase,
)
from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.exceptions import (
    AuthorizationExpiredError,
    DuplicatePaymentError,
    InvalidSignatureError,
    PolicyViolationError,
)
from relayer.domain.services import AuthorizationValidator, PaymentExecutor
from relayer.domain.value_objects import (
    Address, Amount, Nonce, Policy, Signature, TxReceipt,
)


# =====================================================================
# Fakes
# =====================================================================
class FakeClock:
    def __init__(self, t: int) -> None:
        self._t = t
    def now(self) -> int:
        return self._t
    def set(self, t: int) -> None:
        self._t = t


class FixedVerifier:
    def __init__(self, signer: Address) -> None:
        self._signer = signer
    def recover_signer(self, authorization: Authorization) -> Address:
        return self._signer


class InMemoryPaymentRepo:
    """Same interface as PaymentRepository. Backed by dicts."""

    def __init__(self) -> None:
        self._by_id: dict[int, PaymentRequest] = {}
        self._key_to_id: dict[tuple[str, str], int] = {}
        self._next_id = 1

    def save_new(self, payment: PaymentRequest) -> PaymentRequest:
        key = (
            payment.authorization.from_address.value,
            payment.authorization.nonce.to_hex(),
        )
        if key in self._key_to_id:
            raise DuplicatePaymentError(str(key))
        assigned = PaymentRequest(
            id=self._next_id,
            authorization=payment.authorization,
            status=payment.status,
            tx_hash=payment.tx_hash,
            block_number=payment.block_number,
            error=payment.error,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
        self._by_id[assigned.id] = assigned
        self._key_to_id[key] = assigned.id
        self._next_id += 1
        return assigned

    def save(self, payment: PaymentRequest) -> None:
        assert payment.id is not None
        self._by_id[payment.id] = payment

    def get_by_id(self, payment_id: int) -> PaymentRequest | None:
        return self._by_id.get(payment_id)

    def get_by_from_and_nonce(self, from_address, nonce):
        key = (from_address.value, nonce.to_hex())
        pid = self._key_to_id.get(key)
        return self._by_id.get(pid) if pid else None

    def claim_pending(self, limit: int, now: int) -> list[PaymentRequest]:
        claimed: list[PaymentRequest] = []
        for p in list(self._by_id.values()):
            if p.status == PaymentStatus.PENDING:
                updated = p.mark_processing(now)
                self._by_id[updated.id] = updated
                claimed.append(updated)
                if len(claimed) >= limit:
                    break
        return claimed


class FakeUnitOfWork:
    """Snapshot-based rollback."""

    def __init__(self, repo: InMemoryPaymentRepo) -> None:
        self._repo = repo
        self._snapshot: dict[int, PaymentRequest] = {}
        self._key_snapshot: dict[tuple[str, str], int] = {}
        self._next_id_snapshot = 0
        self._committed = False
        self._enter_snapshot()

    def _enter_snapshot(self) -> None:
        # In-memory repo mutation is bounded; snapshot by shallow copy
        self._snapshot = dict(self._repo._by_id)
        self._key_snapshot = dict(self._repo._key_to_id)
        self._next_id_snapshot = self._repo._next_id

    @property
    def payments(self) -> InMemoryPaymentRepo:
        return self._repo

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        self._repo._by_id = dict(self._snapshot)
        self._repo._key_to_id = dict(self._key_snapshot)
        self._repo._next_id = self._next_id_snapshot

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None or not self._committed:
            self.rollback()
        # else: committed, leave as is


class FakeChain:
    def __init__(
        self,
        nonce_used: bool = False,
        submit_raises: Exception | None = None,
        receipt: TxReceipt | None = None,
    ) -> None:
        self.nonce_used = nonce_used
        self.submit_raises = submit_raises
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
        return self.receipt


# =====================================================================
# Fixtures
# =====================================================================
FROM = Address("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
TO = Address("0x1234567890123456789012345678901234567890")
NONCE_HEX = "0x" + "aa" * 32
VALID_AFTER = 1000
VALID_BEFORE = 2000
NOW = 1500
DECIMALS = 6
AMOUNT_RAW = 1_500_000  # 1.5 USDC

SIG_BYTES = b"\x11" * 32 + b"\x22" * 32 + b"\x1b"


def build_input(**overrides) -> SubmitPaymentInput:
    base = dict(
        from_address=FROM.value,
        to_address=TO.value,
        value_raw=str(AMOUNT_RAW),
        valid_after=VALID_AFTER,
        valid_before=VALID_BEFORE,
        nonce=NONCE_HEX,
        v=27,
        r="0x" + "11" * 32,
        s="0x" + "22" * 32,
    )
    base.update(overrides)
    return SubmitPaymentInput(**base)


def build_policy() -> Policy:
    return Policy(
        max_value=Amount.from_human("10", DECIMALS),
        max_validity_window_seconds=7200,
        min_remaining_validity_seconds=60,
        allowed_destinations=None,
    )


def make_submit_use_case(
    clock: FakeClock, repo: InMemoryPaymentRepo
) -> SubmitPaymentUseCase:
    validator = AuthorizationValidator(FixedVerifier(FROM), build_policy())
    return SubmitPaymentUseCase(
        validator=validator,
        uow_factory=lambda: FakeUnitOfWork(repo),
        clock=clock,
        token_decimals=DECIMALS,
    )


# =====================================================================
# Part 1: SubmitPaymentUseCase
# =====================================================================
clock = FakeClock(NOW)
repo = InMemoryPaymentRepo()
submit = make_submit_use_case(clock, repo)

# 1.1 First submit
out1 = submit.execute(build_input())
assert out1.is_duplicate is False
assert out1.status == "pending"
assert out1.request_id == 1

# 1.2 Retry (idempotent)
out2 = submit.execute(build_input())
assert out2.is_duplicate is True
assert out2.request_id == 1
assert out2.status == "pending"

# 1.3 A different nonce creates a new payment
out3 = submit.execute(build_input(nonce="0x" + "bb" * 32))
assert out3.is_duplicate is False
assert out3.request_id == 2

# 1.4 Policy violation (value too high)
try:
    submit.execute(build_input(nonce="0x" + "cc" * 32, value_raw=str(20 * 10**6)))
except PolicyViolationError:
    pass
else:
    raise AssertionError("PolicyViolationError not raised")

# 1.5 Expired authorization
clock.set(VALID_BEFORE + 1)
try:
    submit.execute(build_input(nonce="0x" + "dd" * 32))
except AuthorizationExpiredError:
    pass
else:
    raise AssertionError("AuthorizationExpiredError not raised")
clock.set(NOW)

# 1.6 Malformed r
try:
    submit.execute(build_input(nonce="0x" + "ee" * 32, r="0xZZ"))
except InvalidSignatureError:
    pass
else:
    raise AssertionError("InvalidSignatureError not raised")

print("✅ SubmitPaymentUseCase OK")


# =====================================================================
# Part 2: ExecutePendingPaymentsUseCase
# =====================================================================
clock2 = FakeClock(NOW)
repo2 = InMemoryPaymentRepo()

# Seed two pending payments
for _ in range(2):
    seed = SubmitPaymentUseCase(
        validator=AuthorizationValidator(FixedVerifier(FROM), build_policy()),
        uow_factory=lambda r=repo2: FakeUnitOfWork(r),
        clock=clock2,
        token_decimals=DECIMALS,
    )
    # Use a distinct nonce per call
    n = "0x" + format(repo2._next_id, "064x")
    seed.execute(build_input(nonce=n))

assert len(repo2._by_id) == 2

# Run one batch with a happy-path chain
chain = FakeChain()
executor = PaymentExecutor(chain)
exec_uc = ExecutePendingPaymentsUseCase(
    uow_factory=lambda: FakeUnitOfWork(repo2),
    clock=clock2,
    executor=executor,
)
batch = exec_uc.run_batch(batch_size=10)
assert batch.processed == 2
assert batch.confirmed == 2
assert batch.failed == 0
assert all(r.status == "confirmed" for r in batch.results)

# Idempotent second run: nothing left to claim
batch2 = exec_uc.run_batch(batch_size=10)
assert batch2.processed == 0

print("✅ ExecutePendingPaymentsUseCase (happy path) OK")


# =====================================================================
# Part 3: Execute with a failure path
# =====================================================================
clock3 = FakeClock(NOW)
repo3 = InMemoryPaymentRepo()
seed = SubmitPaymentUseCase(
    validator=AuthorizationValidator(FixedVerifier(FROM), build_policy()),
    uow_factory=lambda: FakeUnitOfWork(repo3),
    clock=clock3,
    token_decimals=DECIMALS,
)
seed.execute(build_input())

# Chain that reverts on-chain
chain_fail = FakeChain(
    receipt=TxReceipt(tx_hash="0xbad", block_number=99, success=False)
)
exec_fail = ExecutePendingPaymentsUseCase(
    uow_factory=lambda: FakeUnitOfWork(repo3),
    clock=clock3,
    executor=PaymentExecutor(chain_fail),
)
batch_fail = exec_fail.run_batch(batch_size=10)
assert batch_fail.processed == 1
assert batch_fail.failed == 1
assert "reverted" in batch_fail.results[0].error.lower()

print("✅ ExecutePendingPaymentsUseCase (revert path) OK")


# =====================================================================
# Part 4: GetPaymentStatusUseCase
# =====================================================================
get_uc = GetPaymentStatusUseCase(uow_factory=lambda: FakeUnitOfWork(repo2))
status = get_uc.execute(request_id=1)
assert status.request_id == 1
assert status.status == "confirmed"
assert status.tx_hash == "0xdead"

try:
    get_uc.execute(request_id=999)
except PaymentNotFoundError:
    pass
else:
    raise AssertionError("PaymentNotFoundError not raised")

print("✅ GetPaymentStatusUseCase OK")
print("\n🎉 Layer 5 (application) OK")
