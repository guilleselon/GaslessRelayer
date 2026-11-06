from relayer.domain.exceptions import (
    InvalidAddressError, InvalidAmountError, InvalidNonceError,
)
from relayer.domain.value_objects import Address, Amount, Nonce


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"{exc_type.__name__} not raised")


# --- Address ---
a = Address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
assert a.value == "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
assert not a.is_zero
assert Address.zero().is_zero
assert_raises(InvalidAddressError, Address, "not-an-address")
assert_raises(InvalidAddressError, Address, "0x123")
assert len(a.to_bytes()) == 20

# --- Amount ---
usdc = Amount.from_human("1.5", decimals=6)
assert usdc.raw == 1_500_000
assert usdc.to_human() == usdc.from_human("1.5", 6).to_human()
assert (Amount.from_human("2", 6) + Amount.from_human("1", 6)).raw == 3_000_000
assert Amount.from_human("2", 6) > Amount.from_human("1", 6)
assert_raises(InvalidAmountError, Amount, -1, 6)
assert_raises(InvalidAmountError, lambda: Amount(1, 6) + Amount(1, 18))

# --- Nonce ---
n = Nonce.from_hex("0x" + "ab" * 32)
assert n.value == bytes.fromhex("ab" * 32)
assert n.to_hex() == "0x" + "ab" * 32
assert_raises(InvalidNonceError, Nonce, b"short")
assert_raises(InvalidNonceError, Nonce.from_hex, "zz")

print("✅ Layer 0 + Layer 1 (exceptions + value objects) OK")
