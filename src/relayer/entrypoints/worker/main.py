"""Worker: consumes pending payments from the queue.

In production (standalone process), installs SIGTERM/SIGINT handlers
for graceful shutdown. In development (threaded inside main.py), skips
signal installation because signals only work in the main thread —
uvicorn installs its own handlers and the daemon thread dies with the
process on Ctrl+C.
"""

from __future__ import annotations

import logging
import signal
import threading

from relayer.config import Settings
from relayer.infrastructure.composition import Container, build_container


logger = logging.getLogger(__name__)


def run(container: Container, settings: Settings) -> None:
    """Main loop. Blocks until the shutdown event is set.

    Safe to run from any thread: only installs signal handlers when
    called from the main thread.
    """
    shutdown = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        logger.info("Received signal %s, shutting down gracefully", signum)
        shutdown.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
        logger.debug("Signal handlers installed (main thread)")
    else:
        logger.debug("Skipping signal handlers (not main thread)")

    logger.info(
        "Worker started: batch_size=%d poll_interval=%.1fs",
        settings.worker_batch_size,
        settings.worker_poll_interval_seconds,
    )

    while not shutdown.is_set():
        try:
            result = container.execute_pending.run_batch(
                batch_size=settings.worker_batch_size
            )
            if result.processed == 0:
                shutdown.wait(settings.worker_poll_interval_seconds)
                continue
            logger.info(
                "Batch: processed=%d confirmed=%d failed=%d",
                result.processed,
                result.confirmed,
                result.failed,
            )
        except Exception:
            logger.exception("Batch failed; retrying after poll interval")
            shutdown.wait(settings.worker_poll_interval_seconds)

    logger.info("Worker stopped")


def main() -> None:
    """Standalone entrypoint (production). Installs signals via run()."""
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    container = build_container(settings.to_config())
    run(container, settings)


if __name__ == "__main__":
    main()
