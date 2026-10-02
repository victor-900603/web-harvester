from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from src.core import Item, Request
from src.core.engine import CrawlerEngine, build_engine
from src.crawler import BaseCrawler


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


def make_engine(mode="sync", concurrency=1, max_retries=1, retry=None):
    engine_cfg = {
        "mode": mode,
        "max_concurrency": concurrency,
        "request_timeout": 30,
        "download_delay": 0,
        "max_retries": max_retries,
    }
    if retry is not None:
        engine_cfg["retry"] = retry
    return CrawlerEngine({"engine": engine_cfg, "request": {}})


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
        from src.core import Response as CoreResponse

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