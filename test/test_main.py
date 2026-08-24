from __future__ import annotations

import pytest

from main import build_cli_limits, build_parser


class TestBuildParser:
    def test_minimal_site(self):
        args = build_parser().parse_args(["--site", "udn_news"])
        assert args.site == "udn_news"

    def test_all_limit_args_parsed(self):
        args = build_parser().parse_args(
            [
                "--site", "udn_news",
                "--max-items", "50",
                "--max-pages", "5",
                "--stop-on-duplicate",
                "--timeout", "120.5",
            ]
        )
        assert args.max_items == 50
        assert args.max_pages == 5
        assert args.stop_on_duplicate is True
        assert args.timeout == 120.5

    def test_no_stop_on_duplicate_flag(self):
        args = build_parser().parse_args(["--site", "udn_news", "--no-stop-on-duplicate"])
        assert args.stop_on_duplicate is False

    def test_stop_on_duplicate_defaults_to_none(self):
        args = build_parser().parse_args(["--site", "udn_news"])
        assert args.stop_on_duplicate is None

    def test_limit_args_default_to_none(self):
        args = build_parser().parse_args(["--site", "udn_news"])
        assert args.max_items is None
        assert args.max_pages is None
        assert args.timeout is None

    def test_invalid_max_items_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--site", "udn_news", "--max-items", "0"])

    def test_invalid_max_pages_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--site", "udn_news", "--max-pages", "-1"])

    def test_invalid_timeout_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--site", "udn_news", "--timeout", "0"])

    def test_non_numeric_max_items_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--site", "udn_news", "--max-items", "abc"])


class TestBuildCliLimits:
    def test_empty_when_no_limit_args(self):
        args = build_parser().parse_args(["--site", "udn_news"])
        assert build_cli_limits(args) == {}

    def test_only_specified_keys_included(self):
        args = build_parser().parse_args(
            ["--site", "udn_news", "--max-items", "50", "--timeout", "90"]
        )
        limits = build_cli_limits(args)
        assert limits == {"max_items": 50, "timeout": 90}

    def test_stop_on_duplicate_false_included(self):
        args = build_parser().parse_args(["--site", "udn_news", "--no-stop-on-duplicate"])
        limits = build_cli_limits(args)
        assert limits == {"stop_on_duplicate": False}

    def test_stop_on_duplicate_true_included(self):
        args = build_parser().parse_args(["--site", "udn_news", "--stop-on-duplicate"])
        limits = build_cli_limits(args)
        assert limits == {"stop_on_duplicate": True}

    def test_all_limit_args(self):
        args = build_parser().parse_args(
            [
                "--site", "udn_news",
                "--max-items", "50",
                "--max-pages", "5",
                "--stop-on-duplicate",
                "--timeout", "120",
            ]
        )
        assert build_cli_limits(args) == {
            "max_items": 50,
            "max_pages": 5,
            "stop_on_duplicate": True,
            "timeout": 120,
        }
