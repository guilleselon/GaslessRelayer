"""Ports: contracts the domain needs from the outside world.

These are Protocol classes: structural typing contracts that any
adapter must satisfy. No implementations live here.
"""

from relayer.domain.ports.chain_gateway import ChainGateway
from relayer.domain.ports.clock import Clock
from relayer.domain.ports.payment_repository import PaymentRepository
from relayer.domain.ports.signature_verifier import SignatureVerifier

__all__ = ["ChainGateway", "Clock", "PaymentRepository", "SignatureVerifier"]
