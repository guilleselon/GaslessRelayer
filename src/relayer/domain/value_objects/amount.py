"""Token amount value object.

Stores amounts in atomic units (the smallest indivisible unit of the
token, e.g., 1 USDC = 1_000_000 atomic units with 6 decimals). This
matches how ERC-20 tokens represent balances on-chain and avoids
floating-point errors entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import total_ordering

from relayer.domain.exceptions import InvalidAmountError

_MAX_DECIMALS = 36


@total_ordering
@dataclass(frozen=True, slots=True)
class Amount:
    """An ERC-20 token amount with its decimals."""

    raw: int
    decimals: int

    def __post_init__(self) -> None:
        if not isinstance(self.raw, int) or isinstance(self.raw, bool):
            raise InvalidAmountError(
                f"raw must be int, got {type(self.raw).__name__}"
            )
        if self.raw < 0:
            raise InvalidAmountError(f"raw cannot be negative: {self.raw}")
        if not isinstance(self.decimals, int) or isinstance(self.decimals, bool):
            raise InvalidAmountError(
                f"decimals must be int, got {type(self.decimals).__name__}"
            )
        if self.decimals < 0 or self.decimals > _MAX_DECIMALS:
            raise InvalidAmountError(
                f"decimals out of range [0, {_MAX_DECIMALS}]: {self.decimals}"
            )

    # --- Constructors ----------------------------------------------------

    @classmethod
    def zero(cls, decimals: int) -> Amount:
        return cls(raw=0, decimals=decimals)

    @classmethod
    def from_human(cls, human: str | int | Decimal, decimals: int) -> Amount:
        """Build an Amount from a human-readable value (e.g., '1.5')."""
        try:
            d = Decimal(str(human))
        except InvalidOperation as e:
            raise InvalidAmountError(f"Invalid decimal value: {human}") from e
        if d < 0:
            raise InvalidAmountError(f"Amount cannot be negative: {human}")
        raw = int(d * (10 ** decimals))
        return cls(raw=raw, decimals=decimals)

    # --- Conversions -----------------------------------------------------

    @property
    def is_zero(self) -> bool:
        return self.raw == 0

    def to_human(self) -> Decimal:
        return Decimal(self.raw) / Decimal(10 ** self.decimals)

    # --- Arithmetic ------------------------------------------------------

    def __add__(self, other: Amount) -> Amount:
        self._require_same_decimals(other)
        return Amount(raw=self.raw + other.raw, decimals=self.decimals)

    def __sub__(self, other: Amount) -> Amount:
        self._require_same_decimals(other)
        if other.raw > self.raw:
            raise InvalidAmountError("Subtraction would result in a negative amount")
        return Amount(raw=self.raw - other.raw, decimals=self.decimals)

    # --- Comparison ------------------------------------------------------

    def __lt__(self, other: Amount) -> bool:
        if not isinstance(other, Amount):
            return NotImplemented
        self._require_same_decimals(other)
        return self.raw < other.raw

    def _require_same_decimals(self, other: Amount) -> None:
        if self.decimals != other.decimals:
            raise InvalidAmountError(
                f"Cannot operate on amounts with different decimals: "
                f"{self.decimals} vs {other.decimals}"
            )

    def __str__(self) -> str:
        return f"{self.to_human()} (raw={self.raw}, decimals={self.decimals})"
