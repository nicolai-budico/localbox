"""Logging setup for localbox.

File logging is only active when a solution root is known.
Logs are written to <solution_root>/.logs/localbox.log with size-based rotation.
"""

import sys
import types
from pathlib import Path

from loguru import logger

# Remove loguru's default stderr handler — Rich handles all console output.
# Loguru is used exclusively for file logging and uncaught exception capture.
logger.remove()

_file_handler_id: int | None = None


def setup_logging(solution_root: Path) -> None:
    """Attach a rotating file handler for the given solution root.

    Safe to call multiple times — only initialises once per process.
    """
    global _file_handler_id
    if _file_handler_id is not None:
        return

    log_dir = solution_root / ".logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    _file_handler_id = logger.add(
        log_dir / "localbox.log",
        rotation="5 MB",
        retention=5,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} {level:<8} {name:<35} {message}",
        backtrace=True,
        diagnose=True,
        enqueue=False,
    )

    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Unhandled exception")
        # Also surface the error to the user — the log handler swallows stderr.
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _excepthook
