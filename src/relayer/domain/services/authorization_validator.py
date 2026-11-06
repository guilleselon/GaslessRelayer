"""Authorization validator.

Applies configurable policy rules to a structurally valid Authorization.
Pure business logic: it only reads its inputs and calls the
SignatureVerifier port. It does not mutate state and does not persist.
"""

from __future__ import annotations

from relayer.domain.entities import Authorization
from relayer.domain.exceptions import (
    AuthorizationExpiredError,
    AuthorizationNotYetValidError,
    InvalidSignatureError,
    PolicyViolationError,
)
from relayer.domain.ports import SignatureVerifier
from relayer.domain.value_objects import Policy


class AuthorizationValidator:
    """Enforces policy + signature validity on authorizations."""

    def __init__(self, verifier: SignatureVerifier, policy: Policy) -> None:
        self._verifier = verifier
        self._policy = policy

    def validate(self, authorization: Authorization, now: int) -> None:
        """Raise a domain exception if the authorization is unacceptable.

        Order matters: cheap checks first, cryptographic verification last.
        """
        # --- 1. Time window: not expired --------------------------------
        if authorization.is_expired(now):
            raise AuthorizationExpiredError(
                f"Authorization expired at {authorization.valid_before}; "
                f"now is {now}"
            )

        # --- 2. Time window: already valid ------------------------------
        if authorization.is_not_yet_valid(now):
            raise AuthorizationNotYetValidError(
                f"Authorization becomes valid at {authorization.valid_after}; "
                f"now is {now}"
            )

        # --- 3. Window size --------------------------------------------
        window = authorization.valid_before - authorization.valid_after
        if window > self._policy.max_validity_window_seconds:
            raise PolicyViolationError(
                f"Authorization window ({window}s) exceeds policy "
                f"({self._policy.max_validity_window_seconds}s)"
            )

        # --- 4. Remaining validity -------------------------------------
        remaining = authorization.valid_before - now
        if remaining < self._policy.min_remaining_validity_seconds:
            raise PolicyViolationError(
                f"Authorization has only {remaining}s remaining; "
                f"policy requires at least "
                f"{self._policy.min_remaining_validity_seconds}s"
            )

        # --- 5. Value limit --------------------------------------------
        if authorization.value > self._policy.max_value:
            raise PolicyViolationError(
                f"Authorization value {authorization.value} exceeds policy "
                f"maximum {self._policy.max_value}"
            )

        # --- 6. Destination allowlist ----------------------------------
        if not self._policy.is_destination_allowed(authorization.to_address):
            raise PolicyViolationError(
                f"Destination {authorization.to_address} is not allowed "
                f"by policy"
            )

        # --- 7. Cryptographic signature (expensive) --------------------
        recovered = self._verifier.recover_signer(authorization)
        if recovered.is_zero:
            raise InvalidSignatureError(
                "ecrecover returned the zero address (malformed signature)"
            )
        if recovered != authorization.from_address:
            raise InvalidSignatureError(
                f"Signature signer {recovered} does not match "
                f"authorization.from_address {authorization.from_address}"
            )
