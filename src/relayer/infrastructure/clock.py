"""System clock adapter."""

from __future__ import annotations

import time


class SystemClock:
    """Returns the current Unix timestamp in seconds."""

    def now(self) -> int:
        return int(time.time())
