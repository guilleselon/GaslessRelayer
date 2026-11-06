"""Domain-level exceptions.

All exceptions here represent violations of business rules.
They are part of the domain's public contract and must never
depend on infrastructure concerns (HTTP codes, DB errors, etc.).
"""


class DomainError(Exception):
    """Base class for all domain-level errors."""


# --- Value object errors -------------------------------------------------

class InvalidAddressError(DomainError):
    """Raised when an Ethereum address is malformed."""


class InvalidAmountError(DomainError):
    """Raised when an Amount violates its invariants."""


class InvalidNonceError(DomainError):
    """Raised when a nonce is not exactly 32 bytes."""


# --- Authorization errors ------------------------------------------------

class InvalidSignatureError(DomainError):
    """Raised when a signature does not match the claimed signer."""


class AuthorizationExpiredError(DomainError):
    """Raised when an authorization's valid_before has passed."""


class AuthorizationNotYetValidError(DomainError):
    """Raised when an authorization's valid_after is in the future."""


class NonceAlreadyUsedError(DomainError):
    """Raised when an authorization's nonce has been consumed on-chain."""


# --- Policy errors -------------------------------------------------------

class PolicyViolationError(DomainError):
    """Raised when an authorization violates a configured policy."""


# --- Payment lifecycle errors --------------------------------------------

class DuplicatePaymentError(DomainError):
    """Raised when a payment with the same (from, nonce) already exists."""


class InvalidStateTransitionError(DomainError):
    """Raised when a PaymentRequest tries to move to an illegal state."""
    
class InvalidAuthorizationError(DomainError):
    """Raised when an Authorization violates structural invariants
    (e.g., zero address, same from/to, empty value, invalid time window)."""
    
class InvalidTxReceiptError(DomainError):
    """Raised when a transaction receipt has malformed fields."""

class InvalidPolicyError(DomainError):
    """Raised when a Policy value object violates its own invariants."""
