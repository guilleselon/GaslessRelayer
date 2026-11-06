"""Verifies each port is implementable with pure-Python fakes.

If a fake implementation is awkward or requires external imports,
the port is leaking infrastructure concerns and must be redesigned.
"""

from relayer.domain.entities import Authorization, PaymentRequest, PaymentStatus
from relayer.domain.ports import (
    ChainGateway,
    Clock,
    PaymentRepository,
    SignatureVerifier,
)
from relayer.domain.value_objects import (
    Address, Amount, Nonce, Signature, TxReceipt,
)


# --- Fakes ------------------------------------------------------------
class FakeClock:
    def __init__(self, t: int) -> None:
        self._t = t

    def now(self) -> int:
        return self._t


class FakeSignatureVerifier:
    def __init__(self, expected: Address) -> None:
        self._expected = expected
        self.calls: list[Authorization] = []

    def recover_signer(self, authorization: Authorization) -> Address:
        self.calls.append(authorization)
        return self._expected


class FakePaymentRepository:
    def __init__(self) -> None:
        self._by_id: dict[int, PaymentRequest] = {}
        self._by_key: dict[tuple[str, str], int] = {}
        self._next_id = 1

    def save_new(self, payment: PaymentRequest) -> PaymentRequest:
        key = (payment.authorization.from_address.value,
               payment.authorization.nonce.to_hex())
        if key in self._by_key:
            from relayer.domain.exceptions import DuplicatePaymentError
            raise DuplicatePaymentError(key)
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
        self._by_key[key] = assigned.id
        self._next_id += 1
        return assigned

    def save(self, payment: PaymentRequest) -> None:
        assert payment.id is not None
        self._by_id[payment.id] = payment

    def get_by_id(self, payment_id: int) -> PaymentRequest | None:
        return self._by_id.get(payment_id)

    def get_by_from_and_nonce(self, from_address: Address, nonce: Nonce):
        key = (from_address.value, nonce.to_hex())
        pid = self._by_key.get(key)
        return self._by_id.get(pid) if pid else None

    def claim_pending(self, limit: int, now: int) -> list[PaymentRequest]:
        claimed: list[PaymentRequest] = []
        for p in self._by_id.values():
            if p.status == PaymentStatus.PENDING:
                updated = p.mark_processing(now)
                self._by_id[updated.id] = updated
                claimed.append(updated)
                if len(claimed) >= limit:
                    break
        return claimed


class FakeChainGateway:
    def __init__(self, tx_receipt: TxReceipt) -> None:
        self._receipt = tx_receipt
        self.transfers: list[Authorization] = []

    def is_nonce_used(self, from_address: Address, nonce: Nonce) -> bool:
        return False

    def transfer_with_authorization(self, authorization: Authorization) -> str:
        self.transfers.append(authorization)
        return self._receipt.tx_hash

    def wait_for_confirmation(self, tx_hash: str) -> TxReceipt:
        assert tx_hash == self._receipt.tx_hash
        return self._receipt


# --- Fixtures ---------------------------------------------------------
def build_authorization() -> Authorization:
    from_addr = Address("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
    to_addr = Address("0x1234567890123456789012345678901234567890")
    return Authorization(
        from_address=from_addr,
        to_address=to_addr,
        value=Amount.from_human("1.5", 6),
        valid_after=1000,
        valid_before=2000,
        nonce=Nonce.from_hex("0x" + "aa" * 32),
        signature=Signature.from_bytes(b"\x11" * 32 + b"\x22" * 32 + b"\x1b"),
    )


# --- Exercise the ports ----------------------------------------------
auth = build_authorization()
clock = FakeClock(1500)
repo = FakePaymentRepository()
verifier = FakeSignatureVerifier(auth.from_address)
chain = FakeChainGateway(TxReceipt(tx_hash="0xdead", block_number=42, success=True))

# 1. Verifier returns the expected signer
recovered = verifier.recover_signer(auth)
assert recovered == auth.from_address
assert verifier.calls == [auth]

# 2. Repository: save_new returns a fresh entity with id
saved = repo.save_new(PaymentRequest.create(auth, clock.now()))
assert saved.id == 1
assert saved.status == PaymentStatus.PENDING

# 3. Repository: get_by_from_and_nonce finds it
found = repo.get_by_from_and_nonce(auth.from_address, auth.nonce)
assert found is not None and found.id == 1

# 4. Repository: duplicate raises
from relayer.domain.exceptions import DuplicatePaymentError
try:
    repo.save_new(PaymentRequest.create(auth, clock.now()))
except DuplicatePaymentError:
    pass
else:
    raise AssertionError("DuplicatePaymentError not raised")

# 5. Repository: claim_pending returns PROCESSING entities
claimed = repo.claim_pending(limit=10, now=clock.now() + 1)
assert len(claimed) == 1
assert claimed[0].status == PaymentStatus.PROCESSING
assert claimed[0].id == 1

# 6. Repository: save persists confirmed
confirmed = claimed[0].mark_confirmed("0xdead", 42, clock.now() + 2)
repo.save(confirmed)
reloaded = repo.get_by_id(1)
assert reloaded is not None and reloaded.status == PaymentStatus.CONFIRMED

# 7. Chain gateway: transfer + wait
tx_hash = chain.transfer_with_authorization(auth)
assert tx_hash == "0xdead"
assert chain.transfers == [auth]
receipt = chain.wait_for_confirmation(tx_hash)
assert receipt == TxReceipt(tx_hash="0xdead", block_number=42, success=True)

print("✅ Layer 3 (ports) OK")
