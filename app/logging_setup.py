"""File + console logging, including hooks for uncaught exceptions."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"


def setup_logging(log_file: Path, console: bool = True) -> None:
    root = logging.getLogger()
    if getattr(root, "_heart_overlay_configured", False):
        return
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2_500_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception:
        pass

    if console and sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(logging.INFO)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    root._heart_overlay_configured = True  # type: ignore[attr-defined]


def install_exception_hooks(on_error=None) -> None:
    """Log uncaught exceptions instead of silently dying in windowed builds."""

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("crash").critical(
            "Uncaught exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        if on_error is not None:
            try:
                on_error(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    sys.excepthook = handle

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        logging.getLogger("crash").critical(
            "Uncaught exception in thread %s:\n%s",
            args.thread.name if args.thread else "?",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    threading.excepthook = thread_hook
