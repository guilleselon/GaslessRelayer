"""Clock port.

Abstracts the concept of 'now' so the domain stays deterministic
and testable. Application services receive a Clock and call now()
when needed, or accept a plain int timestamp from the caller.
"""

from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    """Returns the current Unix timestamp in seconds."""

    def now(self) -> int:
        ...
