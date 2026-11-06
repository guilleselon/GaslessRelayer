"""FastAPI dependency injection: the Container singleton."""

from __future__ import annotations

from functools import lru_cache

from relayer.config import Settings
from relayer.infrastructure.composition import Container, build_container


@lru_cache(maxsize=1)
def _build_default_container() -> Container:
    return build_container(Settings.from_env().to_config())


def get_container() -> Container:
    """FastAPI dependency. Override in tests with app.dependency_overrides."""
    return _build_default_container()
