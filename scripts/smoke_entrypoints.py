"""Smoke test for Layer 7: API + worker entrypoints.

Runs a full HTTP round-trip using TestClient, a real SQLite temp DB,
a real signature verifier, and a fake chain gateway. No network.
"""

import os
import tempfile
import time

from eth_account import Account
from fastapi.testclient import TestClient

from relayer.application.use_cases import (
    ExecutePendingPaymentsUseCase,
    GetPaymentStatusUseCase,
    SubmitPaymentUseCase,
)
from relayer.domain.entities import Authorization
from relayer.domain.services import AuthorizationValidator, PaymentExecutor
from relayer.domain.value_objects import (
    Address, Amount, Policy, Signature, TxReceipt,
)
from relayer.entrypoints.api.dependencies import get_container
from relayer.entrypoints.api.main import app
from relayer.infrastructure.clock import SystemClock
from relayer.infrastructure.composition import Container
from relayer.infrastructure.persistence import (
    init_schema, make_sqlite_uow_factory,
)
from relayer.infrastructure.signature_verifier import Eip712SignatureVerifier


# =====================================================================
# Fake chain
# =====================================================================
class FakeChain:
    def __init__(self):
        self.receipt = TxReceipt(tx_hash="0xdead", block_number=42, success=True)
        self.submitted: list[Authorization] = []

    def is_nonce_used(self, from_address, nonce):
        return False

    def transfer_with_authorization(self, authorization):
        self.submitted.append(authorization)
        return self.receipt.tx_hash

    def wait_for_confirmation(self, tx_hash):
        return self.receipt


# =====================================================================
# Container wired with a real verifier + SQLite + fake chain
# =====================================================================
CHAIN_ID = 11155111
CONTRACT = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
TOKEN_NAME = "USDC"
TOKEN_VERSION = "2"
DECIMALS = 6

db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
init_schema(db_path)
uow_factory = make_sqlite_uow_factory(db_path)

verifier = Eip712SignatureVerifier(
    chain_id=CHAIN_ID,
    verifying_contract=CONTRACT,
    token_name=TOKEN_NAME,
    token_version=TOKEN_VERSION,
)
chain = FakeChain()
clock = SystemClock()
policy = Policy(
    max_value=Amount.from_human("10", DECIMALS),
    max_validity_window_seconds=7200,
    min_remaining_validity_seconds=0,
    allowed_destinations=None,
)
validator = AuthorizationValidator(verifier, policy)

container = Container(
    clock=clock,
    uow_factory=uow_factory,
    chain_gateway=chain,
    submit_payment=SubmitPaymentUseCase(
        validator=validator,
        uow_factory=uow_factory,
        clock=clock,
        token_decimals=DECIMALS,
    ),
    execute_pending=ExecutePendingPaymentsUseCase(
        uow_factory=uow_factory,
        clock=clock,
        executor=PaymentExecutor(chain),
    ),
    get_payment_status=GetPaymentStatusUseCase(uow_factory=uow_factory),
)

app.dependency_overrides[get_container] = lambda: container
client = TestClient(app)


# =====================================================================
# Helpers: sign a real EIP-3009 authorization
# =====================================================================
def sign_authorization(account, to_addr, value_raw, nonce_hex, valid_after, valid_before):
    from eth_account.messages import encode_typed_data
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
        "to": to_addr,
        "value": value_raw,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": bytes.fromhex(nonce_hex[2:]),
    }
    signed = Account.sign_typed_data(
        private_key=account.key,
        domain_data=domain,
        message_types=types,
        message_data=message,
    )
    sig = signed.signature
    return {
        "from": account.address,
        "to": to_addr,
        "value_raw": str(value_raw),
        "valid_after": valid_after,
        "valid_before": valid_before,
        "nonce": nonce_hex,
        "v": sig[64],
        "r": "0x" + sig[0:32].hex(),
        "s": "0x" + sig[32:64].hex(),
    }


# =====================================================================
# Part 1: /health
# =====================================================================
r = client.get("/health")
assert r.status_code == 200, r.text
body = r.json()
assert body["status"] == "ok"
assert body["db_ok"] is True
print("✅ GET /health OK")


# =====================================================================
# Part 2: POST /pay happy path
# =====================================================================
account = Account.create()
to_addr = "0x1234567890123456789012345678901234567890"
now = int(time.time())
nonce_hex = "0x" + "aa" * 32

payload = sign_authorization(
    account, to_addr, 1_500_000, nonce_hex,
    valid_after=now - 100, valid_before=now + 1000,
)

r = client.post("/pay", json=payload)
assert r.status_code == 201, r.text
body = r.json()
assert body["is_duplicate"] is False
assert body["status"] == "pending"
request_id = body["request_id"]
print(f"✅ POST /pay (new) OK, request_id={request_id}")


# =====================================================================
# Part 3: POST /pay idempotent (same signature)
# =====================================================================
r = client.post("/pay", json=payload)
assert r.status_code == 201, r.text
body = r.json()
assert body["is_duplicate"] is True
assert body["request_id"] == request_id
print("✅ POST /pay (duplicate) OK")


# =====================================================================
# Part 4: GET /status/{id}
# =====================================================================
r = client.get(f"/status/{request_id}")
assert r.status_code == 200, r.text
body = r.json()
assert body["status"] == "pending"
assert body["tx_hash"] is None
print("✅ GET /status/{id} (pending) OK")


# =====================================================================
# Part 5: Worker executes, then status becomes confirmed
# =====================================================================
result = container.execute_pending.run_batch(batch_size=10)
assert result.processed == 1
assert result.confirmed == 1

r = client.get(f"/status/{request_id}")
assert r.status_code == 200, r.text
body = r.json()
assert body["status"] == "confirmed"
assert body["tx_hash"] == "0xdead"
assert body["block_number"] == 42
print("✅ GET /status/{id} (confirmed) OK")


# =====================================================================
# Part 6: Error cases
# =====================================================================
# 6.1 Missing field -> 422 (Pydantic)
bad = {k: v for k, v in payload.items() if k != "nonce"}
r = client.post("/pay", json=bad)
assert r.status_code == 422, r.text

# 6.2 Bad field format -> 422 (Pydantic regex)
bad = {**payload, "nonce": "not-a-nonce"}
r = client.post("/pay", json=bad)
assert r.status_code == 422, r.text

# 6.3 Expired authorization -> 400 (domain error)
expired = sign_authorization(
    account, to_addr, 1_000_000, "0x" + "bb" * 32,
    valid_after=now - 1000, valid_before=now - 1,
)
r = client.post("/pay", json=expired)
assert r.status_code == 400, r.text
assert r.json()["error"] == "AuthorizationExpiredError"
print("✅ POST /pay (expired) -> 400 OK")

# 6.4 Policy violation -> 400
too_large = sign_authorization(
    account, to_addr, 20_000_000, "0x" + "cc" * 32,
    valid_after=now - 100, valid_before=now + 1000,
)
r = client.post("/pay", json=too_large)
assert r.status_code == 400, r.text
assert r.json()["error"] == "PolicyViolationError"
print("✅ POST /pay (policy violation) -> 400 OK")

# 6.5 Bad signature (tampered) -> 400
tampered = {**payload, "value_raw": "9999999"}  # different value than signed
tampered["nonce"] = "0x" + "dd" * 32
r = client.post("/pay", json=tampered)
assert r.status_code == 400, r.text
assert r.json()["error"] == "InvalidSignatureError"
print("✅ POST /pay (bad signature) -> 400 OK")

# 6.6 Not found -> 404
r = client.get("/status/99999")
assert r.status_code == 404, r.text
assert r.json()["error"] == "PaymentNotFound"
print("✅ GET /status/{missing} -> 404 OK")


# =====================================================================
# Cleanup
# =====================================================================
os.unlink(db_path)
print("\n🎉 Layer 7 (entrypoints) OK")
