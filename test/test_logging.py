from __future__ import annotations

import logging

import pytest

from src.utils.logging import setup_logging


@pytest.fixture(autouse=True)
def _preserve_root_logger():
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    yield
    root.handlers.clear()
    root.handlers.extend(old_handlers)
    root.setLevel(old_level)


class TestSetupLogging:
    def test_writes_log_file(self, tmp_path):
        log_file = str(tmp_path / "crawler.log")
        setup_logging(level="INFO", log_file=log_file)
        logging.getLogger("test").info("hello")
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = (tmp_path / "crawler.log").read_text(encoding="utf-8")
        assert "hello" in content

    def test_custom_format(self, tmp_path):
        log_file = str(tmp_path / "crawler.log")
        setup_logging(
            level="INFO",
            log_format="%(levelname)s|%(message)s",
            log_file=log_file,
        )
        logging.getLogger("test").info("msg")
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = (tmp_path / "crawler.log").read_text(encoding="utf-8")
        assert "INFO|msg" in content

    def test_no_file_handler_without_log_file(self, tmp_path):
        setup_logging(level="INFO", log_file=None)
        handlers = logging.getLogger().handlers
        assert all(not isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)

    def test_invalid_level_raises(self):
        with pytest.raises(AttributeError):
            setup_logging(level="NOPE")