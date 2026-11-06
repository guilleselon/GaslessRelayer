"""Client: sign an EIP-3009 authorization and submit it to the relayer.

Usage:
    USER_PRIVATE_KEY=0x... DEST_ADDRESS=0x... RECIPIENT_AMOUNT=1.0 \\
        RPC_URL=https://sepolia.infura.io/v3/<project_id> \\
        PYTHONPATH=src python scripts/client_send_payment.py

Environment:
    API_BASE          Relayer base URL (default: http://127.0.0.1:8000)
    RPC_URL           Sepolia RPC endpoint (required; used for the balance
                      sanity check only — the relayer does not trust it)
    USER_PRIVATE_KEY  EOA that signs the authorization (required)
    DEST_ADDRESS      USDC recipient address (required)
    RECIPIENT_AMOUNT  Human-readable amount, e.g. "1.5" (default: "1.0")
"""

import os
import secrets
import time

import httpx
from eth_account import Account
from web3 import Web3


# --- Config ----------------------------------------------------------
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
RPC_URL = os.environ.get("RPC_URL")
if not RPC_URL:
    raise SystemExit(
        "RPC_URL is not set. Example: "
        "RPC_URL=https://sepolia.infura.io/v3/<project_id>"
    )

CHAIN_ID = 11155111
USDC_ADDRESS = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
USDC_NAME = "USDC"
USDC_VERSION = "2"
DECIMALS = 6

USER_PRIVATE_KEY = os.environ["USER_PRIVATE_KEY"]
DEST_ADDRESS = os.environ["DEST_ADDRESS"]      # address that receives USDC
AMOUNT_HUMAN = os.environ.get("RECIPIENT_AMOUNT", "1.0")


# --- Setup -----------------------------------------------------------
user = Account.from_key(USER_PRIVATE_KEY)
w3 = Web3(Web3.HTTPProvider(RPC_URL))

print(f"User:      {user.address}")
print(f"Recipient: {DEST_ADDRESS}")
print(f"Amount:    {AMOUNT_HUMAN} USDC")

# Check the user has USDC (sanity check)
usdc = w3.eth.contract(
    address=w3.to_checksum_address(USDC_ADDRESS),
    abi=[{"inputs": [{"name": "a", "type": "address"}], "name": "balanceOf",
          "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view",
          "type": "function"}],
)
balance = usdc.functions.balanceOf(user.address).call()
print(f"Balance:   {balance / 10**DECIMALS} USDC")
if balance == 0:
    raise SystemExit("User has 0 USDC. Get testnet USDC from https://faucet.circle.com/")


# --- Build the EIP-712 authorization --------------------------------
amount_raw = int(float(AMOUNT_HUMAN) * 10**DECIMALS)
nonce = "0x" + secrets.token_hex(32)
now = int(time.time())
valid_after = now - 60
valid_before = now + 3600  # 1 hour

domain = {
    "name": USDC_NAME,
    "version": USDC_VERSION,
    "chainId": CHAIN_ID,
    "verifyingContract": USDC_ADDRESS,
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
    "from": user.address,
    "to": w3.to_checksum_address(DEST_ADDRESS),
    "value": amount_raw,
    "validAfter": valid_after,
    "validBefore": valid_before,
    "nonce": bytes.fromhex(nonce[2:]),
}

print("\nSigning authorization...")
signed = Account.sign_typed_data(
    private_key=user.key,
    domain_data=domain,
    message_types=types,
    message_data=message,
)
sig = signed.signature

payload = {
    "from": user.address,
    "to": w3.to_checksum_address(DEST_ADDRESS),
    "value_raw": str(amount_raw),
    "valid_after": valid_after,
    "valid_before": valid_before,
    "nonce": nonce,
    "v": sig[64],
    "r": "0x" + sig[0:32].hex(),
    "s": "0x" + sig[32:64].hex(),
}
print("Signed. Submitting to relayer...")


# --- Submit to the API ----------------------------------------------
r = httpx.post(f"{API_BASE}/pay", json=payload, timeout=30)
print(f"POST /pay -> {r.status_code}")
print(f"Response: {r.json()}")

if r.status_code != 201:
    raise SystemExit(f"Relayer rejected the payment: {r.text}")

request_id = r.json()["request_id"]
print(f"\nPayment accepted. request_id={request_id}")
print("Waiting for the worker to execute it on-chain...")


# --- Poll status until terminal --------------------------------------
while True:
    time.sleep(2)
    r = httpx.get(f"{API_BASE}/status/{request_id}", timeout=30)
    status = r.json()
    print(f"  status={status['status']}  tx_hash={status.get('tx_hash')}")

    if status["status"] in ("confirmed", "failed"):
        print(f"\nFinal: {status}")
        if status["status"] == "confirmed":
            print(f"\n✅ Success!")
            print(f"   View on Sepolia Etherscan:")
            print(f"   https://sepolia.etherscan.io/tx/{status['tx_hash']}")
        else:
            print(f"\n❌ Failed: {status.get('error')}")
        break
