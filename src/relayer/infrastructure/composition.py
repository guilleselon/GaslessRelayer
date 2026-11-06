"""Composition root.

Instantiates every adapter and wires the application use cases.
This is the only file that knows which concrete implementations
are used. The rest of the system depends only on ports.

Layer 7 refactor: Container now holds the ChainGateway *port*, not
the Web3UsdcChainGateway adapter. build_container accepts an optional
chain_gateway so tests can inject a FakeChain without touching
network or private keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from relayer.application.unit_of_work import UnitOfWorkFactory
from relayer.application.use_cases import (
    ExecutePendingPaymentsUseCase,
    GetPaymentStatusUseCase,
    SubmitPaymentUseCase,
)
from relayer.domain.ports import ChainGateway
from relayer.domain.services import AuthorizationValidator, PaymentExecutor
from relayer.domain.value_objects import Policy
from relayer.infrastructure.chain_gateway import Web3UsdcChainGateway
from relayer.infrastructure.clock import SystemClock
from relayer.infrastructure.persistence import (
    init_schema,
    make_sqlite_uow_factory,
)
from relayer.infrastructure.signature_verifier import Eip712SignatureVerifier


@dataclass(frozen=True)
class Container:
    """The wired application. Entrypoints consume this, not raw adapters."""

    clock: SystemClock
    uow_factory: UnitOfWorkFactory
    chain_gateway: ChainGateway
    submit_payment: SubmitPaymentUseCase
    execute_pending: ExecutePendingPaymentsUseCase
    get_payment_status: GetPaymentStatusUseCase


@dataclass(frozen=True)
class Config:
    """Everything build_container needs to assemble the system."""

    rpc_url: str
    chain_id: int
    usdc_address: str
    usdc_name: str
    usdc_version: str
    token_decimals: int
    relayer_private_key: str
    db_path: str
    policy: Policy
    confirmations_required: int = 1


def build_container(
    cfg: Config,
    chain_gateway: ChainGateway | None = None,
) -> Container:
    """Wire all adapters and use cases from a Config object.

    Args:
        cfg: Application configuration.
        chain_gateway: Optional override for the ChainGateway port.
            When provided, build_container does NOT instantiate
            Web3UsdcChainGateway, so no RPC connection is made and
            no private key is required. Intended for tests and for
            swapping in alternative gateways (Permit2, other chains).
    """
    # --- Adapters -----------------------------------------------------
    clock = SystemClock()

    init_schema(cfg.db_path)
    uow_factory = make_sqlite_uow_factory(cfg.db_path)

    verifier = Eip712SignatureVerifier(
        chain_id=cfg.chain_id,
        verifying_contract=cfg.usdc_address,
        token_name=cfg.usdc_name,
        token_version=cfg.usdc_version,
    )

    chain: ChainGateway
    if chain_gateway is not None:
        chain = chain_gateway
    else:
        chain = Web3UsdcChainGateway(
            rpc_url=cfg.rpc_url,
            usdc_address=cfg.usdc_address,
            chain_id=cfg.chain_id,
            relayer_private_key=cfg.relayer_private_key,
            confirmations_required=cfg.confirmations_required,
        )

    # --- Domain services ---------------------------------------------
    validator = AuthorizationValidator(verifier, cfg.policy)
    executor = PaymentExecutor(chain)

    # --- Use cases ---------------------------------------------------
    return Container(
        clock=clock,
        uow_factory=uow_factory,
        chain_gateway=chain,
        submit_payment=SubmitPaymentUseCase(
            validator=validator,
            uow_factory=uow_factory,
            clock=clock,
            token_decimals=cfg.token_decimals,
        ),
        execute_pending=ExecutePendingPaymentsUseCase(
            uow_factory=uow_factory,
            clock=clock,
            executor=executor,
        ),
        get_payment_status=GetPaymentStatusUseCase(uow_factory=uow_factory),
    )
