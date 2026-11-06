"""Development entrypoint: runs API + worker in the same process.

For production, run them separately:
  - API:    uvicorn relayer.entrypoints.api.main:app
  - Worker: python -m relayer.entrypoints.worker.main
"""

from __future__ import annotations

import logging
import threading

import uvicorn

from relayer.config import Settings
from relayer.entrypoints.api.dependencies import get_container
from relayer.entrypoints.api.main import app
from relayer.entrypoints.worker.main import run as run_worker


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Warm the container once so both API and worker share it
    container = get_container()

    if settings.worker_enabled:
        worker_thread = threading.Thread(
            target=run_worker,
            args=(container, settings),
            daemon=True,
            name="worker",
        )
        worker_thread.start()

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
