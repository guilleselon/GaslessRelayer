"""Web3/USDC chain gateway.

Implements the ChainGateway port for EIP-3009 tokens on EVM chains.
One instance is bound to one chain and one token contract.
"""

from __future__ import annotations

import time

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TransactionNotFound

from relayer.domain.entities import Authorization
from relayer.domain.value_objects import Address, Nonce, TxReceipt


_USDC_ABI = [
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"},
        ],
        "name": "transferWithAuthorization",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "authorizer", "type": "address"},
            {"name": "nonce", "type": "bytes32"},
        ],
        "name": "authorizationState",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class Web3UsdcChainGateway:
    """ChainGateway implementation for EIP-3009 tokens on EVM."""

    def __init__(
        self,
        rpc_url: str,
        usdc_address: str,
        chain_id: int,
        relayer_private_key: str,
        confirmations_required: int = 1,
        confirmation_timeout_seconds: int = 180,
        gas_limit: int = 300_000,
        max_fee_per_gas_gwei: float = 50.0,
        max_priority_fee_gwei: float = 2.0,
    ) -> None:
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self._w3.is_connected():
            raise RuntimeError(f"RPC unreachable: {rpc_url}")
        self._account: LocalAccount = Account.from_key(relayer_private_key)
        self._usdc = self._w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address),
            abi=_USDC_ABI,
        )
        self._chain_id = chain_id
        self._confirmations = confirmations_required
        self._timeout = confirmation_timeout_seconds
        self._gas_limit = gas_limit
        self._max_fee = self._w3.to_wei(max_fee_per_gas_gwei, "gwei")
        self._max_priority = self._w3.to_wei(max_priority_fee_gwei, "gwei")

    @property
    def relayer_address(self) -> str:
        return self._account.address

    def is_nonce_used(self, from_address: Address, nonce: Nonce) -> bool:
        return self._usdc.functions.authorizationState(
            Web3.to_checksum_address(from_address.value),
            nonce.value,
        ).call()

    def transfer_with_authorization(self, authorization: Authorization) -> str:
        tx = self._usdc.functions.transferWithAuthorization(
            Web3.to_checksum_address(authorization.from_address.value),
            Web3.to_checksum_address(authorization.to_address.value),
            authorization.value.raw,
            authorization.valid_after,
            authorization.valid_before,
            authorization.nonce.value,
            authorization.signature.v,
            authorization.signature.r,
            authorization.signature.s,
        ).build_transaction({
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(
                self._account.address, "pending"
            ),
            "chainId": self._chain_id,
            "gas": self._gas_limit,
            "maxFeePerGas": self._max_fee,
            "maxPriorityFeePerGas": self._max_priority,
        })
        signed = Account.sign_transaction(tx, self._account.key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def wait_for_confirmation(self, tx_hash: str) -> TxReceipt:
        receipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=self._timeout
        )
        # Wait for N confirmations
        while True:
            latest = self._w3.eth.block_number
            if latest - receipt["blockNumber"] + 1 >= self._confirmations:
                break
            time.sleep(2)
        return TxReceipt(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            success=(receipt["status"] == 1),
        )
