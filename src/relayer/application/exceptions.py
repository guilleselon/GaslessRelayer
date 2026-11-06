"""Application-level exceptions.

Distinct from domain exceptions: these represent orchestration failures
(not-found lookups, DTO conversion errors) that the domain never sees.
"""


class ApplicationError(Exception):
    """Base class for application-layer errors."""


class PaymentNotFoundError(ApplicationError):
    """Raised when a requested payment does not exist."""
