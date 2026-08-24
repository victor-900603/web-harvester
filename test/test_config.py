from __future__ import annotations

import os

import pytest

from src.utils.config import (
    ConfigValidationError,
    DEFAULT_SITE_SCHEMA,
    Settings,
    load_site_config,
    merge_limits,
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

    def test_category_normalization_loaded(self):
        settings = Settings()
        assert isinstance(settings.get("category_normalization"), dict)
        assert settings.get("category_normalization.股市") == "財經"

    def test_category_normalization_merged_from_external_file(self):
        settings = Settings()
        norm = settings.get("category_normalization")
        assert "股市" in norm
        assert norm["資通訊"] == "科技"
        assert norm["棒球"] == "運動"


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
            "list_page": {"sources": [{"url": "https://example.com"}]},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_missing_base_url_rejected(self):
        data = {"name": "x", "list_page": {"sources": [{"url": "https://example.com"}]}}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")
        assert "base_url" in str(exc_info.value)

    def test_mixed_selector_styles_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [{"url": "https://example.com"}],
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

    def test_html_field_missing_selector_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "article_page": {
                "type": "html",
                "selectors": {
                    "title": {"type": "text", "path": "data.title"},
                },
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_json_field_missing_path_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "article_page": {
                "type": "json",
                "selectors": {
                    "title": {"type": "text", "selector": "h1.title"},
                },
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")


class TestCategorySchema:
    def test_valid_category_meta_passes(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {
                "sources": [{"type": "meta", "name": "section"}],
                "default": "其他",
            },
        }
        validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_valid_category_all_source_types_pass(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {
                "sources": [
                    {"type": "url", "regex": "/story/(\\d+)/", "mapping": {"1": "A"}},
                    {"type": "meta", "property": "article:section"},
                    {"type": "selector", "selector": "a.breadcrumb", "attr": "text", "join": ">"},
                    {"type": "json_ld", "path": "itemListElement.1.name"},
                    {"type": "list_data", "path": "cate_id"},
                    {"type": "article_json", "path": "data.category"},
                    {"type": "keyword", "rules": [{"keywords": ["a"], "value": "A"}]},
                ],
            },
        }
        validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_category_without_sources_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {"default": "其他"},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_url_source_missing_regex_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {"sources": [{"type": "url"}]},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_meta_source_missing_name_and_property_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {"sources": [{"type": "meta"}]},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_unknown_source_type_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "category": {"sources": [{"type": "bogus", "foo": "bar"}]},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_valid_tags_passes(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "tags": {
                "sources": [{"type": "meta", "name": "news_keywords", "split": ","}],
            },
        }
        validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_tags_unknown_key_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "tags": {"sources": [{"type": "meta", "name": "section"}], "extra": True},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")


class TestListPageSourcesSchema:
    def test_sources_categories_default_valid(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [
                    {"url": "https://example.com/news?page={page}&cat={category}"},
                    {
                        "url": "https://example.com/search?q={keyword}&page={page}",
                        "type": "json",
                    },
                ],
                "categories": {"股市": "7251", "政治": "6645"},
                "category_default": "0",
            },
        }
        validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_source_partial_selectors_valid(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "json",
                "selectors": {"items": "lists", "url_field": "titleLink"},
                "sources": [
                    {
                        "url": "https://example.com/api?page={page}",
                        "selectors": {"url_template": "https://example.com{url}"},
                    },
                ],
            },
        }
        validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_missing_sources_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "url": "https://example.com/news",
                "type": "html",
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_empty_sources_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [],
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_source_without_url_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [{"type": "json"}],
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_source_extra_property_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [{"url": "https://example.com/news", "bogus": "x"}],
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")

    def test_categories_non_string_value_rejected(self):
        data = {
            "name": "x",
            "base_url": "https://example.com",
            "list_page": {
                "type": "html",
                "sources": [{"url": "https://example.com/news?cat={category}"}],
                "categories": {"股市": 7251},
            },
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SITE_SCHEMA, "site")


class TestLoadSiteConfig:
    def test_loads_example_site(self):
        config = load_site_config("example")
        assert config["name"] == "example"

    def test_missing_site_raises(self):
        with pytest.raises(FileNotFoundError):
            load_site_config("no_such_site")


class TestMergeLimits:
    def test_later_source_overrides_earlier(self):
        merged = merge_limits(
            {"max_items": 30, "timeout": 180},
            {"max_items": 10},
        )
        assert merged == {"max_items": 10, "timeout": 180}

    def test_three_layer_precedence(self):
        merged = merge_limits(
            {"max_items": 30, "max_pages": 3, "stop_on_duplicate": True, "timeout": 180},
            {"max_items": 10, "max_pages": 2},
            {"max_items": 5},
        )
        assert merged == {
            "max_items": 5,
            "max_pages": 2,
            "stop_on_duplicate": True,
            "timeout": 180,
        }

    def test_none_values_are_skipped(self):
        merged = merge_limits(
            {"max_items": 30},
            {"max_items": None, "timeout": 180},
        )
        assert merged == {"max_items": 30, "timeout": 180}

    def test_none_and_empty_sources_ignored(self):
        assert merge_limits(None, {}, None) == {}

    def test_all_none_returns_empty(self):
        assert merge_limits() == {}

    def test_does_not_mutate_inputs(self):
        settings = {"max_items": 30}
        site = {"max_items": 10}
        result = merge_limits(settings, site)
        assert settings == {"max_items": 30}
        assert site == {"max_items": 10}
        assert result == {"max_items": 10}


class TestSettingsLimits:
    def test_settings_loads_global_limits(self):
        settings = Settings()
        limits = settings.get("limits")
        assert limits["max_items"] == 100
        assert limits["max_pages"] == 3
        assert limits["stop_on_duplicate"] is False
        assert limits["timeout"] == 180