"""
Bridges the standard `logging` module to Qt signals so the real backend's
log records (INFO/SUCCESS/WARNING/ERROR/DEBUG) stream live into the GUI's
terminal panel. No polling, no subprocess stdout scraping.

A custom SUCCESS level is added because the spec calls for it explicitly
alongside the standard levels.
"""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, Signal

SUCCESS_LEVEL = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def log_success(logger: logging.Logger, msg: str, *args, **kwargs) -> None:
    logger.log(SUCCESS_LEVEL, msg, *args, **kwargs)


# Never let these substrings reach the GUI/log sink, even if a bug upstream
# tries to log them. This is a last-line safety net, not the primary control
# (the primary control is: the code simply never logs these values).
_REDACT_MARKERS = ("API_HASH=", "password=", "2fa_password=")


class _LogSignalCarrier(QObject):
    """Holds the Signal on its own QObject, deliberately separate from
    QtLogHandler. QtLogHandler MUST define a method literally named
    `emit(self, record)` to work as a logging.Handler (the logging module
    calls `self.emit(record)` by that exact name) — but empirically, when
    a Signal lives on the *same* class that also defines a method named
    `emit`, PySide6/Shiboken's signal-binding resolves `self.record_emitted
    .emit(...)` back through that class's own `emit` method instead of the
    Signal's real bound emit, raising a confusing "takes 2 positional
    arguments but N were given" TypeError. Reproduced in isolation with
    both base-class orderings — the collision is the method *name* `emit`
    existing anywhere on the class, not inheritance order. Moving the
    Signal to a separate, unrelated QObject removes the collision."""

    record_emitted = Signal(str, str, str)


class QtLogHandler(logging.Handler):
    """A logging.Handler that emits a Qt signal for every record."""

    def __init__(self):
        super().__init__()
        self._signals = _LogSignalCarrier()
        self.setFormatter(logging.Formatter("%(message)s"))

    @property
    def record_emitted(self):
        """Exposed so callers can do `handler.record_emitted.connect(...)`
        exactly as if the Signal lived directly on this handler."""
        return self._signals.record_emitted

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            for marker in _REDACT_MARKERS:
                if marker in message:
                    message = message.split(marker)[0] + marker + "[hidden]"
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            self._signals.record_emitted.emit(ts, record.levelname, message)
        except Exception:
            self.handleError(record)


def install_gui_logging(handler: QtLogHandler, level: int = logging.INFO) -> None:
    """Attach the handler to the root logger, replacing console-only setup."""
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any pre-existing StreamHandlers so logs aren't duplicated /
    # don't rely on a console the packaged GUI app won't have.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler.setLevel(level)
    root.addHandler(handler)
