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


def make_engine(mode="sync", concurrency=1, max_retries=1):
    return CrawlerEngine(
        {
            "engine": {
                "mode": mode,
                "max_concurrency": concurrency,
                "request_timeout": 30,
                "download_delay": 0,
                "max_retries": max_retries,
            },
            "request": {},
        }
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

    def test_http_error_retries_then_returns_none(self, monkeypatch):
        calls = []

        def failing_fetch(self, request):
            calls.append(request.url)
            raise httpx.HTTPStatusError(
                "404 Client Error",
                request=httpx.Request(request.method, request.url),
                response=httpx.Response(404, request=httpx.Request(request.method, request.url)),
            )

        monkeypatch.setattr(CrawlerEngine, "_fetch_sync", failing_fetch)
        monkeypatch.setattr(time, "sleep", lambda _: None)
        engine = make_engine("sync", max_retries=3)
        crawler = FakeCrawler(["https://e.com/bad"])
        items = engine.run(crawler)
        assert items == []
        assert len(calls) == 3

    def test_fetch_sync_sets_body_for_json(self, monkeypatch):
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
        engine = make_engine("sync")
        resp = engine._fetch_sync(Request(url="https://e.com/a"))
        assert resp is not None
        assert resp.json() == {"ok": True}


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

    def test_timeout_stops_early(self, monkeypatch):
        async def slow_fetch(self, client, request):
            await asyncio.sleep(0.05)
            return _response(request)

        monkeypatch.setattr(CrawlerEngine, "_fetch_async", slow_fetch)
        engine = make_engine("async")
        crawler = FakeCrawler([f"https://e.com/{i}" for i in range(5)], {"timeout": 0.12})
        items = engine.run(crawler)
        assert 0 < len(items) < 5


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


def _fake_sync_process(self, request):
    return _response(request)


async def _fake_async_fetch(self, client, request):
    return _response(request)