from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from src.core import Item, Request
from src.core.engine import CrawlerEngine, build_engine
from src.crawler import BaseCrawler
from src.storage import BaseStorage


class FakeCrawler(BaseCrawler):
    name = "fake"

    def __init__(self, urls, limits=None, emit=None):
        self._urls = list(urls)
        self._limits = limits or {}
        self._emit = emit or {}

    @property
    def limits(self):
        return self._limits

    def start_requests(self):
        for u in self._urls:
            yield Request(url=u, callback="parse")

    def parse(self, response):
        for u in self._emit.get(response.url, []):
            yield Request(url=u)
        yield Item(data={"title": response.url}, source=self.name, url=response.url)


def make_engine(mode="sync", concurrency=1, max_retries=1, retry=None, respect_robots=False, skip_seen_urls=None):
    engine_cfg = {
        "mode": mode,
        "max_concurrency": concurrency,
        "request_timeout": 30,
        "download_delay": 0,
        "max_retries": max_retries,
    }
    if retry is not None:
        engine_cfg["retry"] = retry
    return CrawlerEngine(
        {"engine": engine_cfg, "request": {"respect_robots": respect_robots}},
        skip_seen_urls=skip_seen_urls,
    )


class TestSyncLimits:
    def test_max_items_stops_collection(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _fake_sync_process)
        engine = make_engine("sync")
        crawler = FakeCrawler(["https://e.com/a", "https://e.com/b", "https://e.com/c"], {"max_items": 2})
        items = engine.run(crawler)
        assert len(items) == 2

    def test_stop_on_duplicate_stops(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _fake_sync_process)
        engine = make_engine("sync")
        crawler = FakeCrawler(
            ["https://e.com/a", "https://e.com/b"],
            {"stop_on_duplicate": True},
            emit={"https://e.com/a": ["https://e.com/b", "https://e.com/c"]},
        )
        items = engine.run(crawler)
        assert len(items) == 2

    def test_duplicate_skipped_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _fake_sync_process)
        engine = make_engine("sync")
        crawler = FakeCrawler(
            ["https://e.com/a", "https://e.com/b"],
            {"stop_on_duplicate": False},
            emit={"https://e.com/a": ["https://e.com/b", "https://e.com/c"]},
        )
        items = engine.run(crawler)
        assert len(items) == 3

    def test_post_same_url_different_body_not_deduplicated(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _fake_sync_process)

        class PostCrawler(FakeCrawler):
            def __init__(self):
                super().__init__([])

            def start_requests(self):
                for page in range(3):
                    yield Request(
                        url="https://e.com/list",
                        method="POST",
                        json_body={"pageidx": page},
                        callback="parse",
                    )

            def parse(self, response):
                yield Item(data={"title": response.url}, source=self.name, url=response.url)

        items = make_engine("sync").run(PostCrawler())
        assert len(items) == 3

    def test_post_same_url_same_body_deduplicated(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _fake_sync_process)

        class PostCrawler(FakeCrawler):
            def __init__(self):
                super().__init__([])

            def start_requests(self):
                for _ in range(2):
                    yield Request(
                        url="https://e.com/list",
                        method="POST",
                        body="offset=0",
                        callback="parse",
                    )

            def parse(self, response):
                yield Item(data={"title": response.url}, source=self.name, url=response.url)

        items = make_engine("sync").run(PostCrawler())
        assert len(items) == 1

    def test_timeout_stops_early(self, monkeypatch):
        def slow_process(self, request):
            time.sleep(0.05)
            return _response(request)

        monkeypatch.setattr(CrawlerEngine, "_process_sync", slow_process)
        engine = make_engine("sync")
        crawler = FakeCrawler(
            [f"https://e.com/{i}" for i in range(5)],
            {"timeout": 0.12},
        )
        items = engine.run(crawler)
        assert 0 < len(items) < 5

    def test_invalid_mode_raises(self):
        engine = make_engine("turbo")
        with pytest.raises(ValueError):
            engine.run(FakeCrawler(["https://e.com/a"]))

    def test_retryable_error_retries_then_returns_none(self, monkeypatch):
        calls = []

        def failing_fetch(self, request):
            calls.append(request.url)
            raise _status_error(request, 503)

        monkeypatch.setattr(CrawlerEngine, "_fetch_sync", failing_fetch)
        monkeypatch.setattr(time, "sleep", lambda _: None)
        engine = make_engine("sync", max_retries=3)
        crawler = FakeCrawler(["https://e.com/bad"])
        items = engine.run(crawler)
        assert items == []
        assert len(calls) == 3

    def test_non_retryable_error_fails_fast(self, monkeypatch):
        calls = []

        def failing_fetch(self, request):
            calls.append(request.url)
            raise _status_error(request, 404)

        sleeps = []
        monkeypatch.setattr(CrawlerEngine, "_fetch_sync", failing_fetch)
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        engine = make_engine("sync", max_retries=3)
        crawler = FakeCrawler(["https://e.com/bad"])
        items = engine.run(crawler)
        assert items == []
        assert len(calls) == 1
        assert sleeps == []

    def test_retry_after_header_is_honored(self, monkeypatch):
        def failing_fetch(self, request):
            raise _status_error(request, 429, {"Retry-After": "7"})

        sleeps = []
        monkeypatch.setattr(CrawlerEngine, "_fetch_sync", failing_fetch)
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        engine = make_engine("sync", max_retries=2, retry={"jitter": "none", "max_delay": 100})
        engine.run(FakeCrawler(["https://e.com/limited"]))
        assert sleeps == [7.0]

    def test_backoff_delay_used_between_retries(self, monkeypatch):
        def failing_fetch(self, request):
            raise _status_error(request, 500)

        sleeps = []
        monkeypatch.setattr(CrawlerEngine, "_fetch_sync", failing_fetch)
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        engine = make_engine("sync", max_retries=3, retry={"base_delay": 2, "jitter": "none"})
        engine.run(FakeCrawler(["https://e.com/flaky"]))
        assert sleeps == [2.0, 4.0]

    def test_fetch_sync_sets_body_for_json(self, monkeypatch):
        # Engine now delegates to http_client; test via httpx path explicitly
        from src.core.http_client import HttpxClient

        class FakeResponse:
            status_code = 200
            encoding = "utf-8"
            content = b'{"ok": true}'
            text = '{"ok": true}'
            headers = {}
            cookies = {}

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def request(self, *args, **kwargs):
                return FakeResponse()

        monkeypatch.setattr(httpx, "Client", FakeClient)
        # Force httpx client regardless of default curl_cffi
        client = HttpxClient(timeout=5, verify_ssl=True, user_agent="test/1.0")
        engine = make_engine("sync")
        # inject httpx client
        engine._http_client = client
        resp = engine._fetch_sync(Request(url="https://e.com/a"))
        assert resp is not None
        assert resp.json() == {"ok": True}

        # Also verify CurlCffiClient path with mocked session
        import sys
        import types

        class FakeCurlResp:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            cookies = {}
            text = '{"ok": true}'
            content = b'{"ok": true}'
            encoding = "utf-8"

        class FakeSession:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, **kwargs):
                return FakeCurlResp()

        fake_crequests = types.ModuleType("curl_cffi.requests")
        fake_crequests.Session = FakeSession
        fake_curl = types.ModuleType("curl_cffi")
        fake_curl.requests = fake_crequests
        monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl)
        monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_crequests)

        from src.core.http_client import CurlCffiClient

        curl_client = CurlCffiClient(impersonate="chrome131")
        engine2 = make_engine("sync")
        engine2._http_client = curl_client
        resp2 = engine2._fetch_sync(Request(url="https://e.com/a"))
        assert resp2 is not None
        assert resp2.json() == {"ok": True}


class TestAsyncLimits:
    def test_max_items_stops_collection(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _fake_async_fetch)
        engine = make_engine("async")
        crawler = FakeCrawler(["https://e.com/a", "https://e.com/b", "https://e.com/c"], {"max_items": 2})
        items = engine.run(crawler)
        assert len(items) == 2

    def test_stop_on_duplicate_stops(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _fake_async_fetch)
        engine = make_engine("async")
        crawler = FakeCrawler(
            ["https://e.com/a", "https://e.com/b"],
            {"stop_on_duplicate": True},
            emit={"https://e.com/a": ["https://e.com/b", "https://e.com/c"]},
        )
        items = engine.run(crawler)
        assert len(items) == 2

    def test_duplicate_skipped_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _fake_async_fetch)
        engine = make_engine("async")
        crawler = FakeCrawler(
            ["https://e.com/a", "https://e.com/b"],
            {"stop_on_duplicate": False},
            emit={"https://e.com/a": ["https://e.com/b", "https://e.com/c"]},
        )
        items = engine.run(crawler)
        assert len(items) == 3

    def test_post_same_url_different_body_not_deduplicated(self, monkeypatch):
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _fake_async_fetch)

        class PostCrawler(FakeCrawler):
            def __init__(self):
                super().__init__([])

            def start_requests(self):
                for page in range(3):
                    yield Request(
                        url="https://e.com/list",
                        method="POST",
                        json_body={"pageidx": page},
                        callback="parse",
                    )

            def parse(self, response):
                yield Item(data={"title": response.url}, source=self.name, url=response.url)

        items = make_engine("async").run(PostCrawler())
        assert len(items) == 3

    def test_timeout_stops_early(self, monkeypatch):
        async def slow_fetch(self, request):
            await asyncio.sleep(0.05)
            return _response(request)

        monkeypatch.setattr(CrawlerEngine, "_fetch_async", slow_fetch)
        engine = make_engine("async")
        crawler = FakeCrawler([f"https://e.com/{i}" for i in range(5)], {"timeout": 0.12})
        items = engine.run(crawler)
        assert 0 < len(items) < 5

    def test_retryable_error_retries_then_returns_none(self, monkeypatch):
        calls = []

        async def failing_fetch(self, request):
            calls.append(request.url)
            raise _status_error(request, 503)

        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(CrawlerEngine, "_fetch_async", failing_fetch)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        engine = make_engine("async", max_retries=3, retry={"jitter": "none"})
        items = engine.run(FakeCrawler(["https://e.com/bad"]))
        assert items == []
        assert len(calls) == 3
        assert len(sleeps) == 2

    def test_non_retryable_error_fails_fast(self, monkeypatch):
        calls = []

        async def failing_fetch(self, request):
            calls.append(request.url)
            raise _status_error(request, 404)

        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(CrawlerEngine, "_fetch_async", failing_fetch)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        engine = make_engine("async", max_retries=3)
        items = engine.run(FakeCrawler(["https://e.com/bad"]))
        assert items == []
        assert len(calls) == 1
        assert sleeps == []

    def test_retry_after_header_is_honored(self, monkeypatch):
        async def failing_fetch(self, request):
            raise _status_error(request, 429, {"Retry-After": "9"})

        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(CrawlerEngine, "_fetch_async", failing_fetch)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        engine = make_engine("async", max_retries=2, retry={"jitter": "none", "max_delay": 100})
        engine.run(FakeCrawler(["https://e.com/limited"]))
        assert sleeps == [9.0]


class TestBuildEngine:
    def test_disabled_storage(self, tmp_path):
        settings = {
            "json_storage": {"enabled": False},
            "database": {"enabled": False},
        }
        engine = build_engine(settings)
        assert engine.storages == []
        engine.close()

    def test_enabled_storage_mounted(self, tmp_path):
        settings = {
            "json_storage": {"enabled": True, "output_dir": str(tmp_path)},
            "database": {"enabled": True, "url": f"sqlite:///{tmp_path}/t.db"},
        }
        engine = build_engine(settings)
        assert len(engine.storages) == 2
        engine.close()


def _response(request):
    from src.core import Response

    return Response(url=request.url, status_code=200, text="<html></html>", request=request)


def _status_error(request, status_code, headers=None):
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=httpx.Request(request.method, request.url),
        response=httpx.Response(status_code, headers=headers or {}, request=httpx.Request(request.method, request.url)),
    )


def _fake_sync_process(self, request):
    return _response(request)


async def _fake_async_fetch(self, request):
    return _response(request)


class KnownURLStorage(BaseStorage):
    """Storage stub that reports a fixed set of already stored URLs."""

    def __init__(self, urls=()):
        self._urls = set(urls)

    def save(self, item):
        self._urls.add(item.url)

    def known_urls(self):
        return set(self._urls)


class FakeRobots:
    """Robots policy stub driven by an explicit allowlist."""

    def __init__(self, allowed_urls):
        self.allowed_urls = set(allowed_urls)

    def allowed(self, url):
        return url in self.allowed_urls

    async def allowed_async(self, url):
        return url in self.allowed_urls


def _counting_process(calls):
    def fake_process(self, request):
        calls.append(request.url)
        return _response(request)

    return fake_process


def _counting_async_fetch(calls):
    async def fake_fetch(self, request):
        calls.append(request.url)
        return _response(request)

    return fake_fetch


class TestSkipSeenURLs:
    def test_known_url_is_not_fetched(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync")
        engine.add_storage(KnownURLStorage({"https://e.com/old"}))
        crawler = FakeCrawler(["https://e.com/old", "https://e.com/new"])
        items = engine.run(crawler)
        assert calls == ["https://e.com/new"]
        assert [item.url for item in items] == ["https://e.com/new"]
        assert engine._skipped_known == 1

    def test_skipped_when_disabled(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync", skip_seen_urls=False)
        engine.add_storage(KnownURLStorage({"https://e.com/old"}))
        crawler = FakeCrawler(["https://e.com/old"])
        items = engine.run(crawler)
        assert calls == ["https://e.com/old"]
        assert len(items) == 1
        assert engine._skipped_known == 0

    def test_known_url_stops_when_stop_on_duplicate(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync")
        engine.add_storage(KnownURLStorage({"https://e.com/old"}))
        crawler = FakeCrawler(["https://e.com/old", "https://e.com/new"], {"stop_on_duplicate": True})
        items = engine.run(crawler)
        assert calls == []
        assert items == []

    def test_no_storage_means_no_skipping(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync")
        crawler = FakeCrawler(["https://e.com/a", "https://e.com/b"])
        items = engine.run(crawler)
        assert len(calls) == 2
        assert len(items) == 2

    def test_known_url_skipped_in_async_mode(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _counting_async_fetch(calls))
        engine = make_engine("async")
        engine.add_storage(KnownURLStorage({"https://e.com/old"}))
        items = engine.run(FakeCrawler(["https://e.com/old", "https://e.com/new"]))
        assert calls == ["https://e.com/new"]
        assert len(items) == 1
        assert engine._skipped_known == 1

    def test_storage_failure_does_not_abort_run(self, monkeypatch, caplog):
        class BrokenStorage(BaseStorage):
            def save(self, item):
                pass

            def known_urls(self):
                raise RuntimeError("db down")

        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync")
        engine.add_storage(BrokenStorage())
        items = engine.run(FakeCrawler(["https://e.com/a"]))
        assert len(items) == 1
        assert any("Failed to load known URLs" in rec.getMessage() for rec in caplog.records)


class TestRobotsEnforcement:
    def test_disallowed_url_is_not_fetched(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync", respect_robots=True)
        engine._robots = FakeRobots({"https://e.com/allowed"})
        items = engine.run(FakeCrawler(["https://e.com/allowed", "https://e.com/blocked"]))
        assert calls == ["https://e.com/allowed"]
        assert len(items) == 1
        assert engine._skipped_robots == 1

    def test_disabled_by_settings(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync", respect_robots=False)
        engine._robots = FakeRobots(set())
        items = engine.run(FakeCrawler(["https://e.com/blocked"]))
        assert len(calls) == 1
        assert len(items) == 1
        assert engine._skipped_robots == 0

    def test_site_override_disables_check(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync", respect_robots=True)
        engine._robots = FakeRobots(set())

        class SiteOverrideCrawler(FakeCrawler):
            @property
            def respect_robots(self):
                return False

        items = engine.run(SiteOverrideCrawler(["https://e.com/blocked"]))
        assert len(calls) == 1
        assert len(items) == 1

    def test_site_override_enables_check(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_process_sync", _counting_process(calls))
        engine = make_engine("sync", respect_robots=False)
        engine._robots = FakeRobots(set())

        class SiteOverrideCrawler(FakeCrawler):
            @property
            def respect_robots(self):
                return True

        items = engine.run(SiteOverrideCrawler(["https://e.com/blocked"]))
        assert calls == []
        assert items == []
        assert engine._skipped_robots == 1

    def test_disallowed_in_async_mode(self, monkeypatch):
        calls = []
        monkeypatch.setattr(CrawlerEngine, "_fetch_async", _counting_async_fetch(calls))
        engine = make_engine("async", respect_robots=True)
        engine._robots = FakeRobots(set())
        items = engine.run(FakeCrawler(["https://e.com/blocked"]))
        assert calls == []
        assert items == []
        assert engine._skipped_robots == 1


class TestBuildEngineSkipSeen:
    def test_cli_override_is_applied(self, tmp_path):
        settings = {
            "engine": {"skip_seen_urls": True},
            "json_storage": {"enabled": False},
            "database": {"enabled": False},
        }
        engine = build_engine(settings, skip_seen_urls=False)
        assert engine._skip_seen_urls is False
        engine.close()

    def test_configured_value_is_used_when_no_override(self, tmp_path):
        settings = {
            "engine": {"skip_seen_urls": False},
            "json_storage": {"enabled": False},
            "database": {"enabled": False},
        }
        engine = build_engine(settings)
        assert engine._skip_seen_urls is False
        engine.close()
