"""Signal handler setup for graceful service shutdown."""

import signal

from idea_shared.classes.Logger import Logger

logger = Logger(__name__)


def setup_sync_signal_handlers(shutdown_handler) -> None:
    """Register SIGTERM and SIGINT handlers for synchronous services.

    Args:
        shutdown_handler: Callable(signum, frame) to handle shutdown.

    """
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    logger.info("Signal handlers registered for graceful shutdown")
