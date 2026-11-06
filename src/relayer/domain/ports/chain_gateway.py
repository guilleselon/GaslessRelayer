"""Chain gateway port.

Abstracts all on-chain interaction. One implementation per chain
(Ethereum, Base, Polygon, ...) and per authorization scheme
(EIP-3009, Permit2, ...). The application layer selects an adapter
via dependency injection at the composition root.
"""

from __future__ import annotations

from typing import Protocol

from relayer.domain.entities import Authorization
from relayer.domain.value_objects import Address, Nonce, TxReceipt


class ChainGateway(Protocol):
    """A blockchain adapter capable of executing authorizations."""

    def is_nonce_used(self, from_address: Address, nonce: Nonce) -> bool:
        """Return True if the authorization nonce has been consumed on-chain.

        This is a pre-flight check. A False return does not guarantee
        the subsequent transfer will succeed (another party may consume
        the nonce in between), but a True return means the transfer is
        definitively unnecessary.
        """
        ...

    def transfer_with_authorization(self, authorization: Authorization) -> str:
        """Submit the on-chain transfer and return the transaction hash.

        Must NOT wait for confirmation. Must NOT raise on on-chain
        reverts (those are detected via wait_for_confirmation); only
        raise on submission failures (RPC unreachable, insufficient
        balance for gas, nonce collision at the RPC layer).
        """
        ...

    def wait_for_confirmation(self, tx_hash: str) -> TxReceipt:
        """Block until the transaction is mined and return its receipt.

        Returns a TxReceipt with success=False if the transaction
        reverted. The implementation decides how many confirmations
        to require based on its configuration.
        """
        ...
