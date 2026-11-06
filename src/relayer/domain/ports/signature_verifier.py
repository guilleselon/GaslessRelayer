"""Signature verification port.

Recovers the signer address from an EIP-712 authorization. The
comparison with the expected signer is a policy decision that
belongs to the application layer, not to this port.
"""

from __future__ import annotations

from typing import Protocol

from relayer.domain.entities import Authorization
from relayer.domain.value_objects import Address


class SignatureVerifier(Protocol):
    """Recovers the address that signed an EIP-3009 authorization."""

    def recover_signer(self, authorization: Authorization) -> Address:
        """Return the address recovered from the authorization's signature.

        Implementations must:
          - Rebuild the EIP-712 digest exactly as the token contract does.
          - Use ecrecover semantics (v in {27, 28}).
          - Return Address.zero() if the signature is malformed (bad
            r/s range, invalid v), matching ecrecover's behavior.

        The caller is responsible for rejecting Address.zero() and for
        comparing the result with authorization.from_address.
        """
        ...
