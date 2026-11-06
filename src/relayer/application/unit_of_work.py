"""Unit of Work port.

Defines an atomic boundary for one or more repository operations.
The factory callable returns a fresh UnitOfWork per use, ensuring
transactional isolation between operations and thread safety.
"""

from __future__ import annotations

from types import TracebackType
from typing import Callable, Protocol

from relayer.domain.ports import PaymentRepository


class UnitOfWork(Protocol):
    """An atomic transaction boundary exposing repositories."""

    @property
    def payments(self) -> PaymentRepository:
        """The payment repository bound to this transaction."""
        ...

    def commit(self) -> None:
        """Persist all changes made in this unit of work."""
        ...

    def rollback(self) -> None:
        """Discard all changes made in this unit of work."""
        ...

    def __enter__(self) -> UnitOfWork:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Implementations must rollback if no commit() was called.
        ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
