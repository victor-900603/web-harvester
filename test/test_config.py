from __future__ import annotations

import os

import pytest

from src.utils.config import (
    ConfigValidationError,
    DEFAULT_SITE_SCHEMA,
    Settings,
    load_site_config,
    validate_config,
)


class TestSettings:
    def test_loads_default_config(self):
        settings = Settings()
        assert settings.get("app.name") == "news-crawler"
        assert settings.get("engine.mode") in ("sync", "async")

    def test_get_missing_key_returns_default(self):
        settings = Settings()
        assert settings.get("nonexistent.key", "fallback") == "fallback"
        assert settings.get("engine.nonexistent") is None

    def test_set_and_get(self):
        settings = Settings()
        settings.set("custom.nested.value", 42)
        assert settings.get("custom.nested.value") == 42

    def test_missing_config_file_uses_empty(self, tmp_path):
        settings = Settings(config_path=str(tmp_path / "missing.yaml"))
        assert settings.get("engine.mode") is None

    def test_invalid_yaml_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("engine: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigValidationError):
            Settings(config_path=str(bad))

    def test_invalid_engine_mode_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "app: {name: x, version: 1}\nengine: {mode: turbo}\nlogging: {level: INFO}\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            Settings(config_path=str(bad))
        assert "engine.mode" in str(exc_info.value)


class TestValidateConfig:
    def test_valid_settings_passes(self):
        from src.utils.config import DEFAULT_SETTINGS_SCHEMA

        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "logging": {"level": "INFO"},
            "json_storage": {"enabled": True},
            "database": {"enabled": True},
        }
        validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_unknown_key_rejected(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "logging": {"level": "INFO"},
            "typo_key": True,
        }
        from src.utils.config import DEFAULT_SETTINGS_SCHEMA

        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_invalid_base_url_rejected(self):
        data = {
            "name": "x",
            "base_url": "ftp://example.com",
            "list_page": {"url": "https://example.com", "type": "html"},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_missing_base_url_rejected(self):
        data = {"name": "x", "list_page": {"url": "https://example.com", "type": "html"}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")
        assert "base_url" in str(exc_info.value)

    def test_mixed_selector_styles_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "url": "https://example.com",
                "type": "html",
                "selectors": {
                    "items": "a",
                    "link": "a",
                    "link_attr": "href",
                    "url_field": "url",
                },
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_error_message_contains_path(self):
        data = {"name": "x", "base_url": 123}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")
        assert "base_url" in str(exc_info.value)


class TestLoadSiteConfig:
    def test_loads_example_site(self):
        config = load_site_config("example")
        assert config["name"] == "example"
        assert config["site_id"] == "example"

    def test_missing_site_raises(self):
        with pytest.raises(FileNotFoundError):
            load_site_config("no_such_site")