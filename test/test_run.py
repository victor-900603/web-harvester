from __future__ import annotations

import pytest

from web_harvester import cli as main


class TestParser:
    def test_site_required(self):
        parser = main.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([])
        assert exc.value.code == 2

    def test_site_and_list_sites_mutually_exclusive(self):
        parser = main.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--site", "example", "--list-sites"])
        assert exc.value.code == 2

    def test_site_argument_accepted(self):
        parser = main.build_parser()
        args = parser.parse_args(["--site", "example"])
        assert args.site == "example"

    def test_list_sites_flag(self):
        parser = main.build_parser()
        args = parser.parse_args(["--list-sites"])
        assert args.list_sites is True

    def test_keyword_and_category_arguments(self):
        parser = main.build_parser()
        args = parser.parse_args(["--site", "example", "--keyword", "股市", "--category", "財經"])
        assert args.keyword == "股市"
        assert args.category == "財經"

    def test_keyword_short_flag(self):
        parser = main.build_parser()
        args = parser.parse_args(["--site", "example", "-k", "股市", "-c", "財經"])
        assert args.keyword == "股市"
        assert args.category == "財經"


class TestListSites:
    def test_lists_available_sites(self, monkeypatch, capsys):
        monkeypatch.setattr(main, "get_all_site_ids", lambda **kwargs: ["example", "udn_news"])
        assert main.list_sites() == 0
        out = capsys.readouterr().out
        assert "example" in out
        assert "udn_news" in out

    def test_empty_sites_returns_error(self, monkeypatch, capsys):
        monkeypatch.setattr(main, "get_all_site_ids", lambda **kwargs: [])
        assert main.list_sites() == 1
        err = capsys.readouterr().err
        assert "No site configs found" in err


class TestMain:
    def test_site_loads_and_runs(self, monkeypatch):
        captured = {}

        def fake_load(site_id, **kwargs):
            captured["site_id"] = site_id
            return {"name": "example"}

        def fake_settings(**kwargs):
            class FakeSettings:
                def get(self, key, default=None):
                    return {"logging.level": "INFO"}.get(key, default)

            return FakeSettings()

        def fake_setup(**kwargs):
            captured["setup"] = kwargs

        class FakeEngine:
            def __init__(self, settings, **kwargs):
                captured["engine_settings"] = settings
                captured["engine_kwargs"] = kwargs

            skipped_articles = 0

            def run(self, crawler):
                captured["crawler"] = crawler
                return []

        monkeypatch.setattr(main, "load_site_config", fake_load)
        monkeypatch.setattr(main, "Settings", fake_settings)
        monkeypatch.setattr(main, "setup_logging", fake_setup)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: ("crawler", cfg, kw))

        code = main.main(["--site", "example"])
        assert code == 0
        assert captured["site_id"] == "example"
        assert captured["crawler"] == (
            "crawler",
            {"name": "example"},
            {
                "category_normalization": None,
                "keyword": None,
                "category": None,
                "default_limits": None,
                "limit_overrides": {},
            },
        )

    def test_keyword_and_category_passed_to_crawler(self, monkeypatch):
        captured = {}

        def fake_load(site_id, **kwargs):
            return {"name": "example"}

        def fake_settings(**kwargs):
            class FakeSettings:
                def get(self, key, default=None):
                    return {"logging.level": "INFO"}.get(key, default)

            return FakeSettings()

        def fake_setup(**kwargs):
            pass

        class FakeEngine:
            def __init__(self, settings, **kwargs):
                pass

            skipped_articles = 0

            def run(self, crawler):
                captured["crawler"] = crawler
                return []

        monkeypatch.setattr(main, "load_site_config", fake_load)
        monkeypatch.setattr(main, "Settings", fake_settings)
        monkeypatch.setattr(main, "setup_logging", fake_setup)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: ("crawler", cfg, kw))

        code = main.main(["--site", "example", "--keyword", "股市", "--category", "財經"])
        assert code == 0
        assert captured["crawler"] == (
            "crawler",
            {"name": "example"},
            {
                "category_normalization": None,
                "keyword": "股市",
                "category": "財經",
                "default_limits": None,
                "limit_overrides": {},
            },
        )

    def test_skip_seen_flags_forwarded_to_engine(self, monkeypatch):
        captured = []

        def fake_load(site_id, **kwargs):
            return {"name": "example"}

        class FakeSettings:
            def __init__(self, **kwargs):
                pass

            def get(self, key, default=None):
                return {"logging.level": "INFO"}.get(key, default)

        class FakeEngine:
            def __init__(self, settings, **kwargs):
                captured.append(kwargs)

            skipped_articles = 0

            def run(self, crawler):
                return []

        monkeypatch.setattr(main, "load_site_config", fake_load)
        monkeypatch.setattr(main, "Settings", FakeSettings)
        monkeypatch.setattr(main, "setup_logging", lambda **kw: None)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: "crawler")

        assert main.main(["--site", "example"]) == 0
        assert main.main(["--site", "example", "--skip-seen"]) == 0
        assert main.main(["--site", "example", "--no-skip-seen"]) == 0

        assert captured == [
            {"skip_seen_urls": None, "dry_run": False},
            {"skip_seen_urls": True, "dry_run": False},
            {"skip_seen_urls": False, "dry_run": False},
        ]

    def test_unknown_site_errors(self, monkeypatch, capsys):
        def fake_load(site_id, **kwargs):
            raise FileNotFoundError(f"Site config file config/sites/{site_id}.yaml not found.")

        monkeypatch.setattr(main, "load_site_config", fake_load)
        with pytest.raises(SystemExit) as exc:
            main.main(["--site", "nope"])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "nope" in err

    def test_list_sites_shortcut(self, monkeypatch):
        monkeypatch.setattr(main, "get_all_site_ids", lambda **kwargs: ["example"])
        code = main.main(["--list-sites"])
        assert code == 0


class TestAllSitesOption:
    def test_all_sites_and_site_are_mutually_exclusive(self):
        parser = main.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--site", "example", "--all-sites"])
        assert exc.value.code == 2

    def test_runs_every_site_and_prints_summary(self, monkeypatch, capsys):
        class FakeSettings:
            def __init__(self, **kwargs):
                pass

            def get(self, key, default=None):
                return {"logging.level": "INFO"}.get(key, default)

        class FakeEngine:
            skipped_articles = 0

            def __init__(self, settings, **kwargs):
                pass

            def run(self, crawler):
                return ["item"]

        monkeypatch.setattr(main, "get_all_site_ids", lambda **kwargs: ["alpha", "beta"])
        monkeypatch.setattr(main, "load_site_config", lambda site_id, **kw: {"name": site_id})
        monkeypatch.setattr(main, "Settings", FakeSettings)
        monkeypatch.setattr(main, "setup_logging", lambda **kw: None)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: cfg)

        assert main.main(["--all-sites"]) == 0
        out = capsys.readouterr().out
        assert "Crawl summary:" in out
        assert "alpha" in out and "beta" in out
        assert "items=2" in out

    def test_broken_site_is_skipped_and_run_fails(self, monkeypatch, capsys):
        def fake_load(site_id, **kwargs):
            if site_id == "beta":
                raise FileNotFoundError("missing")
            return {"name": site_id}

        class FakeSettings:
            def __init__(self, **kwargs):
                pass

            def get(self, key, default=None):
                return {"logging.level": "INFO"}.get(key, default)

        class FakeEngine:
            skipped_articles = 0

            def __init__(self, settings, **kwargs):
                pass

            def run(self, crawler):
                return []

        monkeypatch.setattr(main, "get_all_site_ids", lambda **kwargs: ["alpha", "beta"])
        monkeypatch.setattr(main, "load_site_config", fake_load)
        monkeypatch.setattr(main, "Settings", FakeSettings)
        monkeypatch.setattr(main, "setup_logging", lambda **kw: None)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: cfg)

        assert main.main(["--all-sites"]) == 1
        assert "Skipping beta" in capsys.readouterr().err


class TestDryRunOption:
    def test_dry_run_forwarded_and_reported(self, monkeypatch, capsys):
        captured = {}

        class FakeSettings:
            def __init__(self, **kwargs):
                pass

            def get(self, key, default=None):
                return {"logging.level": "INFO"}.get(key, default)

        class FakeEngine:
            skipped_articles = 4

            def __init__(self, settings, **kwargs):
                captured.update(kwargs)

            def run(self, crawler):
                return []

        monkeypatch.setattr(main, "load_site_config", lambda site_id, **kw: {"name": site_id})
        monkeypatch.setattr(main, "Settings", FakeSettings)
        monkeypatch.setattr(main, "setup_logging", lambda **kw: None)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: cfg)

        assert main.main(["--site", "example", "--dry-run"]) == 0
        assert captured["dry_run"] is True
        out = capsys.readouterr().out
        assert "4 article page(s) would be fetched" in out


class TestConfigDirOption:
    def test_missing_config_dir_returns_error(self, tmp_path, capsys):
        assert main.main(["--site", "example", "--config-dir", str(tmp_path)]) == 2
        assert "Configuration error" in capsys.readouterr().err

    def test_config_dir_forwarded_to_loader(self, tmp_path, monkeypatch):
        (tmp_path / "settings.yaml").write_text("app: {}\n", encoding="utf-8")
        captured = {}

        def fake_load(site_id, **kwargs):
            captured.update(kwargs)
            return {"name": site_id}

        class FakeSettings:
            def __init__(self, **kwargs):
                pass

            def get(self, key, default=None):
                return {"logging.level": "INFO"}.get(key, default)

        class FakeEngine:
            skipped_articles = 0

            def __init__(self, settings, **kwargs):
                pass

            def run(self, crawler):
                return []

        monkeypatch.setattr(main, "load_site_config", fake_load)
        monkeypatch.setattr(main, "Settings", FakeSettings)
        monkeypatch.setattr(main, "setup_logging", lambda **kw: None)
        monkeypatch.setattr(main, "build_engine", FakeEngine)
        monkeypatch.setattr(main, "SiteCrawler", lambda cfg, **kw: cfg)

        assert main.main(["--site", "example", "--config-dir", str(tmp_path)]) == 0
        assert captured["config_dir"] == tmp_path.resolve()
