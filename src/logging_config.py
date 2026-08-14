import logging
import re
from collections.abc import Mapping
from typing import Any


_TOKEN_PATTERN = re.compile(r"([?&]token=)[^&\s\"']+", re.IGNORECASE)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _TOKEN_PATTERN.sub(r"\1[REDACTED]", value)
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact(item) for key, item in value.items()}
    return value


class SensitiveQueryFilter(logging.Filter):
    """Prevent credentials carried in query strings from reaching application logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        record.args = _redact(record.args)
        return True


def install_sensitive_log_filter() -> None:
    # WebSocket handshake messages are emitted by uvicorn.error; normal HTTP access lines use
    # uvicorn.access. Attach to both handlers because logger propagation/config differs between
    # uvicorn versions and deployment environments.
    query_filter = SensitiveQueryFilter()
    for logger_name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(query_filter)
        for handler in logger.handlers:
            handler.addFilter(query_filter)
