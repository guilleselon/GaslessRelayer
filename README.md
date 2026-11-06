# Gasless Relayer — MVP

> ⚠️ **This is a learning MVP, not a production product.**
>
> It works end-to-end on a testnet, but it has known limitations
> (documented below) that make it unsafe to run in production or
> with real funds. Use it as a reference implementation to learn
> the EIP-3009 gasless pattern and the hexagonal architecture it
> demonstrates, then build your own production version on top of
> what works here.

A small backend that sponsors gas for **USDC transfers using EIP-3009**.
A user signs an off-chain authorization; the relayer submits the
on-chain `transferWithAuthorization` and pays the gas. The user never
needs ETH.

---

## What it does

Without this service, a user holding only USDC still needs ETH to move
it. With EIP-3009, the user signs a `TransferWithAuthorization` off-chain
and **anyone** can present that signature to the USDC contract. This
service is that "anyone": it validates the signature and policy, queues
the payment, and executes it on-chain, absorbing the gas cost.

The service is **not** a business by itself. It does not charge the user.
Monetization is out of scope of this MVP.

---

## How it works

```
User (wallet / script)
  │  signs EIP-712 TransferWithAuthorization off-chain
  │  POST /pay  { from, to, value_raw, valid_after, valid_before,
  │               nonce, v, r, s }
  ▼
API  →  SubmitPaymentUseCase
        ├─ parse primitives into domain VOs (Authorization)
        ├─ AuthorizationValidator.validate()
        │     time window → policy (max value, allowlist, max window)
        │     → signature (ecrecover)
        └─ persist PENDING in SQLite
              (UNIQUE(from_addr, nonce_hex) = idempotency)
  │  201 { request_id, status: "pending" }
  ▼
Worker  →  ExecutePendingPaymentsUseCase
        ├─ claim_pending: PENDING → PROCESSING (one transaction)
        └─ per payment: PaymentExecutor.execute()
              ├─ chain.is_nonce_used(from, nonce)     ← pre-flight
              ├─ chain.transfer_with_authorization()  ← relayer sends tx
              └─ chain.wait_for_confirmation(tx_hash) → CONFIRMED | FAILED
  ▼
User  →  GET /status/{id}  until confirmed | failed
```

On-chain, the relayer's EOA is `msg.sender`. The USDC contract verifies
the signature, checks `block.timestamp` against `validAfter`/`validBefore`,
consumes the nonce, and moves USDC from `from` to `to`. The relayer pays
gas; the user pays only the transferred amount.

---

## Architecture

Hexagonal (ports & adapters). Dependencies point inward, always.

```
entrypoints/      FastAPI routes + worker loop          (frameworks)
    │
infrastructure/   SQLite, web3, eth_account, system     (adapters)
    │
application/      Use cases, DTOs, UnitOfWork           (orchestration)
    │
domain/           Entities, VOs, ports, services        (business rules)
```

| Layer | Responsibility | Knows about |
|---|---|---|
| `domain/` | Entities (`Authorization`, `PaymentRequest`), value objects (`Address`, `Amount`, `Nonce`, `Signature`, `Policy`), ports (`Protocol`s), services (`AuthorizationValidator`, `PaymentExecutor`) | Nothing external |
| `application/` | Three use cases + DTOs + `UnitOfWork` | `domain/` only |
| `infrastructure/` | `Eip712SignatureVerifier`, `Web3UsdcChainGateway`, `SQLitePaymentRepository`, `SQLiteUnitOfWork`, `SystemClock`, composition root | `domain/` + third-party libs |
| `entrypoints/` | FastAPI app, worker loop | `application/`, `infrastructure/` |

The only file that knows concrete implementations is
`infrastructure/composition.py`. Everything else depends on ports.

---

## Project layout

```
.
├── .env.example
├── main.py                          # dev: API + worker in one process
├── pyproject.toml
├── scripts/
│   ├── client_send_payment.py       # EOA client: sign + POST + poll
│   ├── reconcile_failed.py          # ops: fix FAILED rows that actually mined
│   └── test_*.py                    # pytest suite (discovered via testpaths)
├── src/relayer/
│   ├── config/                      # env-driven Settings
│   ├── domain/                      # core (no external deps)
│   ├── application/                 # use cases
│   ├── infrastructure/              # adapters + composition root
│   └── entrypoints/
│       ├── api/                     # FastAPI
│       └── worker/                  # standalone worker entrypoint
└── smoke_domain.py … smoke_entrypoints.py   # per-layer contract scripts (repo root)
```

`pyproject.toml` sets `testpaths = ["tests", "scripts"]`, so pytest
looks for `test_*.py` files in both directories. Today the suite lives
in `scripts/`; the `tests/` entry is there for future growth.

---

## Quickstart

### 1. Prerequisites

- Python **3.11+**
- A **testnet** with a USDC deployment that supports EIP-3009.
  The defaults target **Sepolia** (`CHAIN_ID=11155111`,
  `USDC_ADDRESS=0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`).
- Two EOAs:
  - **Relayer**: needs testnet ETH for gas.
  - **User**: needs testnet USDC. Get it from
    [faucet.circle.com](https://faucet.circle.com/).

### 2. Install (editable, because of the `src/` layout)

```bash
git clone <your-fork> gasless-relayer
cd gasless-relayer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`pip install -e .` is what makes `import relayer` work from anywhere.
Without it, `python main.py` fails with `ModuleNotFoundError`. If you
prefer not to install, use `PYTHONPATH=src python main.py`.

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`. **Do not commit it.** At minimum:

```dotenv
RPC_URL=https://sepolia.infura.io/v3/<your_project_id>
RELAYER_PRIVATE_KEY=0x...      # testnet-only, freshly generated
DB_PATH=relayer.db
MAX_VALUE_PER_TX_RAW=1000000000   # 1000 USDC (6 decimals)
```

Optional knobs (all have sane defaults):

```dotenv
CONFIRMATIONS_REQUIRED=1
CONFIRMATION_TIMEOUT_SECONDS=180
GAS_LIMIT=300000
MAX_FEE_PER_GAS_GWEI=50.0
MAX_PRIORITY_FEE_GWEI=2.0
```

### 4. Verify the EIP-712 domain (important)

The EIP-712 `name` and `version` must match the on-chain USDC contract
**exactly**. If they don't, your signatures will verify locally but the
transaction will revert on-chain with `invalid signature`.

```bash
cast call 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238 "name()(string)"    --rpc-url $RPC_URL
cast call 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238 "version()(string)" --rpc-url $RPC_URL
```

Update `USDC_NAME` / `USDC_VERSION` in `.env` to match. Repeat on every
chain you target — Circle's deployments have used different values.

### 5. Run

```bash
python main.py
```

This starts the FastAPI app on `127.0.0.1:8000` **and** a worker thread
in the same process. For production-like running, separate them:

```bash
uvicorn relayer.entrypoints.api.main:app --host 127.0.0.1 --port 8000
python -m relayer.entrypoints.worker.main
```

### 6. Send a payment

```bash
USER_PRIVATE_KEY=0x... \
DEST_ADDRESS=0x... \
RECIPIENT_AMOUNT=1.0 \
RPC_URL=$RPC_URL \
python scripts/client_send_payment.py
```

The script prints the tx hash and a Sepolia Etherscan link on success.

### 7. Manual API calls (optional)

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/status/1
# POST /pay needs a full signed payload (see scripts/client_send_payment.py)
```

---

## Testing

Two independent test suites live in the repo.

### `scripts/test_*.py` — pytest suite (the main one)

Discovered automatically because `pyproject.toml` sets
`testpaths = ["tests", "scripts"]` and `pythonpath = ["src"]`. No
installation required for the import to resolve. Run it with:

```bash
pytest
# or, if you haven't done `pip install -e .`:
PYTHONPATH=src pytest
```

### `smoke_*.py` — per-layer contract scripts (repo root)

Standalone scripts, one per layer. They run top-to-bottom as a module
and exit non-zero on the first failing `assert`. They are intentionally
*not* `test_*.py` so pytest doesn't pick them up, and they don't need
network access. Run them individually:

```bash
PYTHONPATH=src python smoke_domain.py
PYTHONPATH=src python smoke_entities.py
PYTHONPATH=src python smoke_ports.py
PYTHONPATH=src python smoke_services.py
PYTHONPATH=src python smoke_application.py
PYTHONPATH=src python smoke_infrastructure.py
PYTHONPATH=src python smoke_entrypoints.py
```

What each one covers:

| File | Layer | Network? |
|---|---|---|
| `smoke_domain.py` | Value objects | no |
| `smoke_entities.py` | Entities, transitions | no |
| `smoke_ports.py` | Ports implementable with fakes | no |
| `smoke_services.py` | `AuthorizationValidator`, `PaymentExecutor` | no |
| `smoke_application.py` | Use cases with fake UoW + fake chain | no |
| `smoke_infrastructure.py` | SQLite, real EIP-712 sign+recover | no |
| `smoke_entrypoints.py` | FastAPI round-trip with `TestClient` | no |

`smoke_infrastructure.py` does **not** exercise `Web3UsdcChainGateway`
— it says so explicitly. On-chain coverage of that adapter is a
separate concern (integration test against a real testnet RPC).

---

## Known limitations

These are documented on purpose. Some are TODO items; some are
architectural limits of the MVP.

### 🔴 Will bite you in production

1. **Nonce race between workers.** `Web3UsdcChainGateway` reads
   `get_transaction_count(..., "pending")` per submission. Two
   concurrent workers get the same pending nonce; one tx fails with
   `nonce too low`. **The system is only correct with a single worker.**
   Fix: a nonce manager (local counter seeded once, atomic increment,
   resync on error), or force one submitter process.

2. **No reorg handling.** `CONFIRMED` is terminal today. With
   `CONFIRMATIONS_REQUIRED=1`, a reorg can revert a payment already
   marked confirmed. Fix: a `FINALIZED` state after N confirmations,
   plus a reorg monitor.

3. **No `PROCESSING` reconciliation.** If the process crashes between
   `claim_pending` (commit) and the final `save`, the payment stays
   `PROCESSING` forever. `reconcile_failed.py` only handles
   `status='failed' AND tx_hash IS NOT NULL`. Fix: a dedicated use case
   that scans stuck `PROCESSING` rows and consults the chain.

4. **No authentication on `/pay`.** Anyone with a valid signature can
   burn the relayer's gas. The policy layer (max value, allowlist) is
   the only guard. Fix: API keys or HMAC-signed requests.

5. **No CORS.** `create_app()` doesn't mount `CORSMiddleware`. A browser
   frontend at a different origin can't call `POST /pay`. Fix: add
   `CORSMiddleware` in `entrypoints/api/main.py`.

6. **No MEV protection.** The relayer submits to the public mempool.
   A bot can front-run the signature and submit the same authorization
   with a higher gas price. The relayer pays gas for a reverted tx.
   Fix: private RPC (Flashbots Protect, MEV Blocker).

7. **`USDC_NAME` / `USDC_VERSION` are not validated against the chain.**
   Wrong values cause signatures to verify locally but revert on-chain.
   Fix: `Eip712SignatureVerifier.__init__` should read `name()` and
   `version()` from the contract and fail if they don't match.

### 🟡 Paper cuts, not blockers

8. **`reconcile_failed.py` bypasses the `UnitOfWork`** and uses
   `sqlite3` directly. It duplicates the schema knowledge. Cosmetic
   for an ops script; risky if the schema changes.

9. **`smoke_*.py` are not part of the pytest suite.** They live at the
   repo root and aren't discovered by `pytest` (only `scripts/test_*.py`
   is). If you want them in CI, either move them into `scripts/` with a
   `test_*.py` prefix, or wrap each in a `conftest.py`.

10. **`smoke_*.py` use module-level `assert`.** With `python -O` they
    silently skip. Wrap them in `main()` functions called explicitly
    if you ever run them under optimization.

11. **`Container` holds `clock` and `chain_gateway` as unused fields.**
    Reserved for future health checks. Harmless.

12. **`main.py` imports `app` at module load**, so `create_app()` runs
    before `Settings.from_env()`. Not a bug, but the order means you
    can't fail-fast on missing env before the app object exists.

### 🟢 Things that are fine for an MVP

- No metrics, no tracing, no structured logs (only `logging.basicConfig`).
- No rate limiting.
- Single token, single chain, single relayer EOA.
- SQLite (fine for a demo; Postgres for multi-instance).
- No graceful worker shutdown beyond `SIGTERM` → `Event.set()`.

---

## Path to production

If you want to turn this into something real, in priority order:

1. **Nonce manager** — the single most important fix. Either
   serialize submissions in one process, or maintain a local nonce
   counter with a lock and resync on error.
2. **Verify `USDC_NAME` / `USDC_VERSION` on-chain at startup** and
   fail closed if they don't match the config.
3. **`PROCESSING` reconciliation use case** + a scheduled job.
4. **Auth on `/pay`** (API keys minimum).
5. **CORS** if serving a browser frontend.
6. **Private mempool RPC** to avoid front-running.
7. **Reorg handling** (`FINALIZED` after N confirmations).
8. **Real integration test** against Sepolia for `Web3UsdcChainGateway`.
9. **Metrics + structured logs**.
10. **Postgres** if you need >1 worker.

---

## Security notes

- **Never commit a private key.** `.env` should be in `.gitignore`.
- **Use a dedicated testnet-only EOA** for the relayer. Rotate it if
  it ever appears in a log, transcript, or screenshot.
- **Never run this against mainnet with real funds** without addressing
  the "Will bite you in production" list above.
- **The `Amount.from_human` helper** is exact. Don't reintroduce
  `float` arithmetic for token amounts in clients — `float("0.3") * 1e6`
  is `299999.99999999994`, which truncates to `299999`.

---

## License

MIT. It's a learning project. Fork it, learn from it, build something
better. No warranty, no support, no production readiness implied.
