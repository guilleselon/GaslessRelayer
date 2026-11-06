"""EIP-712 signature verifier.

Rebuilds the EIP-3009 TransferWithAuthorization digest exactly as
FiatTokenV2_2 does, and recovers the signer via ecrecover semantics.
"""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_typed_data

from relayer.domain.entities import Authorization
from relayer.domain.value_objects import Address


_TRANSFER_WITH_AUTHORIZATION_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


class Eip712SignatureVerifier:
    """Recovers EIP-3009 signers using eth_account."""

    def __init__(
        self,
        chain_id: int,
        verifying_contract: str,
        token_name: str,
        token_version: str,
    ) -> None:
        self._domain = {
            "name": token_name,
            "version": token_version,
            "chainId": chain_id,
            "verifyingContract": verifying_contract,
        }

    def recover_signer(self, authorization: Authorization) -> Address:
        message = {
            "from": authorization.from_address.value,
            "to": authorization.to_address.value,
            "value": authorization.value.raw,
            "validAfter": authorization.valid_after,
            "validBefore": authorization.valid_before,
            "nonce": authorization.nonce.value,
        }
        try:
            encoded = encode_typed_data(
                domain_data=self._domain,
                message_types=_TRANSFER_WITH_AUTHORIZATION_TYPES,
                message_data=message,
            )
            recovered = Account.recover_message(
                encoded, signature=authorization.signature.to_bytes()
            )
        except Exception:
            # Malformed signature (bad r/s range, invalid v) -> zero address,
            # matching ecrecover's behavior on-chain.
            return Address.zero()
        return Address(recovered)
