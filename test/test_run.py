from __future__ import annotations

import pytest

import main


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
        monkeypatch.setattr(main, "get_all_site_ids", lambda: ["example", "udn_news"])
        assert main.list_sites() == 0
        out = capsys.readouterr().out
        assert "example" in out
        assert "udn_news" in out

    def test_empty_sites_returns_error(self, monkeypatch, capsys):
        monkeypatch.setattr(main, "get_all_site_ids", lambda: [])
        assert main.list_sites() == 1
        err = capsys.readouterr().err
        assert "No site configs found" in err


class TestMain:
    def test_site_loads_and_runs(self, monkeypatch):
        captured = {}

        def fake_load(site_id):
            captured["site_id"] = site_id
            return {"name": "example"}

        def fake_settings():
            class FakeSettings:
                def get(self, key, default=None):
                    return {"logging.level": "INFO"}.get(key, default)

            return FakeSettings()

        def fake_setup(**kwargs):
            captured["setup"] = kwargs

        class FakeEngine:
            def __init__(self, settings):
                captured["engine_settings"] = settings

            def run(self, crawler):
                captured["crawler"] = crawler

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
            {"category_normalization": None, "keyword": None, "category": None},
        )

    def test_keyword_and_category_passed_to_crawler(self, monkeypatch):
        captured = {}

        def fake_load(site_id):
            return {"name": "example"}

        def fake_settings():
            class FakeSettings:
                def get(self, key, default=None):
                    return {"logging.level": "INFO"}.get(key, default)

            return FakeSettings()

        def fake_setup(**kwargs):
            pass

        class FakeEngine:
            def __init__(self, settings):
                pass

            def run(self, crawler):
                captured["crawler"] = crawler

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
            {"category_normalization": None, "keyword": "股市", "category": "財經"},
        )

    def test_unknown_site_errors(self, monkeypatch, capsys):
        def fake_load(site_id):
            raise FileNotFoundError(f"Site config file config/sites/{site_id}.yaml not found.")

        monkeypatch.setattr(main, "load_site_config", fake_load)
        with pytest.raises(SystemExit) as exc:
            main.main(["--site", "nope"])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "nope" in err

    def test_list_sites_shortcut(self, monkeypatch):
        monkeypatch.setattr(main, "get_all_site_ids", lambda: ["example"])
        code = main.main(["--list-sites"])
        assert code == 0