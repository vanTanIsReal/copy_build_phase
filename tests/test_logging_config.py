import logging

from src.logging_config import SensitiveQueryFilter


def test_websocket_token_is_redacted_from_log_arguments():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:1234", "/api/v1/ws?token=secret.jwt.value&mode=chat"),
        None,
    )

    assert SensitiveQueryFilter().filter(record)
    rendered = record.getMessage()
    assert "secret.jwt.value" not in rendered
    assert "/api/v1/ws?token=[REDACTED]&mode=chat" in rendered
