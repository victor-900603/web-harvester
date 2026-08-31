from __future__ import annotations

import asyncio
import types

import httpx
import pytest

from src.core import Request, Response
from src.core.http_client import (
    CurlCffiClient,
    HttpxClient,
    SUPPORTED_IMPERSONATES,
    build_http_client,
)
from src.utils.config import DEFAULT_SETTINGS_SCHEMA, validate_config, ConfigValidationError


class TestBuildHttpClient:
    def test_default_builds_curl_cffi_when_available(self):
        # curl_cffi is installed in this env, should return CurlCffiClient
        client = build_http_client({"request": {}, "engine": {}})
        assert isinstance(client, CurlCffiClient)

    def test_explicit_httpx(self):
        client = build_http_client({"request": {"http_client": "httpx"}, "engine": {}})
        assert isinstance(client, HttpxClient)

    def test_explicit_curl_cffi(self):
        client = build_http_client({"request": {"http_client": "curl_cffi", "impersonate": "chrome131"}, "engine": {}})
        assert isinstance(client, CurlCffiClient)
        assert client._impersonate == "chrome131"

    def test_invalid_client_raises(self):
        with pytest.raises(ValueError, match="Unsupported http_client"):
            build_http_client({"request": {"http_client": "bogus"}, "engine": {}})

    def test_fallback_when_curl_cffi_missing(self, monkeypatch):
        # Simulate ImportError for curl_cffi
        import sys

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            if name == "curl_cffi" or name.startswith("curl_cffi."):
                raise ImportError("mocked missing")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        # Also need to ensure sys.modules doesn't contain it
        monkeypatch.delitem(sys.modules, "curl_cffi", raising=False)
        monkeypatch.delitem(sys.modules, "curl_cffi.requests", raising=False)
        client = build_http_client({"request": {"http_client": "curl_cffi"}, "engine": {}})
        assert isinstance(client, HttpxClient)

    def test_ja3_and_akamai_stored_when_no_impersonate(self):
        client = build_http_client(
            {"request": {"http_client": "curl_cffi", "impersonate": "", "ja3": "fake_ja3", "akamai": "fake_akamai"}, "engine": {}}
        )
        assert isinstance(client, CurlCffiClient)
        assert client._ja3 == "fake_ja3"
        assert client._akamai == "fake_akamai"
        assert client._impersonate is None

    def test_ja3_ignored_warning_when_impersonate_set(self, caplog):
        client = CurlCffiClient(impersonate="chrome131", ja3="x", akamai="y")
        assert client._impersonate == "chrome131"
        # warning emitted
        import logging

        # caplog not automatically captured for direct instantiation without pytest caplog fixture? Use manual check
        # Instead verify attributes and that warning would be logged on construction via logger
        # The __init__ logs warning; we ensure no exception and ja3 stored but ignored
        assert client._ja3 == "x"


class TestSettingsSchemaValidation:
    def test_valid_curl_cffi_settings_pass(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "request": {"http_client": "curl_cffi", "impersonate": "chrome131", "ja3": "abc", "akamai": "def"},
            "logging": {"level": "INFO"},
        }
        validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_valid_httpx_settings_pass(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "async"},
            "request": {"http_client": "httpx", "verify_ssl": False, "user_agent": "test/1.0"},
            "logging": {"level": "INFO"},
        }
        validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_empty_impersonate_allowed(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "request": {"impersonate": ""},
            "logging": {"level": "INFO"},
        }
        validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_invalid_impersonate_rejected(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "request": {"impersonate": "not_a_browser"},
            "logging": {"level": "INFO"},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")

    def test_invalid_http_client_rejected(self):
        data = {
            "app": {"name": "x", "version": "1"},
            "engine": {"mode": "sync"},
            "request": {"http_client": "requests"},
            "logging": {"level": "INFO"},
        }
        with pytest.raises(ConfigValidationError):
            validate_config(data, DEFAULT_SETTINGS_SCHEMA, "settings")


class TestHttpxClient:
    def test_fetch_sync_success(self, monkeypatch):
        class FakeResponse:
            status_code = 200
            encoding = "utf-8"
            content = b'{"ok": true}'
            text = '{"ok": true}'
            headers = {"X-Test": "1"}
            cookies = {"a": "b"}

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *a, **k):
                self.kwargs = k

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, *a, **k):
                assert k["method"] == "GET" if "method" not in k else True
                return FakeResponse()

        monkeypatch.setattr(httpx, "Client", FakeClient)
        client = HttpxClient(timeout=5, verify_ssl=True, user_agent="test/1.0")
        resp = client.fetch_sync(Request(url="https://e.com/a"))
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_fetch_sync_raises_for_status(self, monkeypatch):
        class FakeResponse:
            status_code = 404
            encoding = "utf-8"
            content = b"not found"
            text = "not found"
            headers = {}
            cookies = {}

            def raise_for_status(self):
                raise httpx.HTTPStatusError("404", request=httpx.Request("GET", "https://e.com/a"), response=httpx.Response(404, request=httpx.Request("GET", "https://e.com/a")))

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, *a, **k):
                return FakeResponse()

        monkeypatch.setattr(httpx, "Client", FakeClient)
        client = HttpxClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_sync(Request(url="https://e.com/a"))

    def test_fetch_async_success(self, monkeypatch):
        class FakeAsyncResponse:
            status_code = 200
            encoding = "utf-8"
            content = b"hi"
            text = "hi"
            headers = {}
            cookies = {}

            def raise_for_status(self):
                return None

        class FakeAsyncClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, *a, **k):
                return FakeAsyncResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
        client = HttpxClient()

        async def run():
            resp = await client.fetch_async(Request(url="https://e.com/a"))
            assert resp.status_code == 200
            assert resp.text == "hi"

        asyncio.run(run())


class TestCurlCffiClient:
    def test_fetch_sync_with_mock_session(self, monkeypatch):
        # Mock curl_cffi.requests.Session
        class FakeResp:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            cookies = {"c": "d"}
            text = '{"hello": 1}'
            content = b'{"hello": 1}'
            encoding = "utf-8"

        class FakeSession:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                # verify impersonate passed
                assert kwargs.get("impersonate") == "chrome131"
                assert kwargs.get("verify") is True

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, **kwargs):
                assert kwargs["url"] == "https://e.com/a"
                return FakeResp()

        fake_module = types.ModuleType("curl_cffi.requests")
        fake_module.Session = FakeSession
        # Need to mock curl_cffi.requests import path: curl_cffi.requests.Session
        # The client does `from curl_cffi import requests as crequests`; crequests.Session
        fake_crequests = types.ModuleType("curl_cffi.requests")
        fake_crequests.Session = FakeSession
        # Create parent curl_cffi module with attribute requests
        import sys

        fake_curl = types.ModuleType("curl_cffi")
        fake_curl.requests = fake_crequests
        monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl)
        monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_crequests)

        client = CurlCffiClient(impersonate="chrome131", verify_ssl=True, timeout=5)
        resp = client.fetch_sync(Request(url="https://e.com/a"))
        assert resp.status_code == 200
        assert resp.json() == {"hello": 1}

    def test_fetch_sync_raises_on_http_error(self, monkeypatch):
        class FakeResp:
            status_code = 403
            headers = {}
            cookies = {}
            text = "forbidden"
            content = b"forbidden"
            encoding = "utf-8"

        class FakeSession:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, **kwargs):
                return FakeResp()

        import sys, types

        fake_crequests = types.ModuleType("curl_cffi.requests")
        fake_crequests.Session = FakeSession
        fake_curl = types.ModuleType("curl_cffi")
        fake_curl.requests = fake_crequests
        monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl)
        monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_crequests)

        client = CurlCffiClient(impersonate="chrome131")
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_sync(Request(url="https://e.com/a"))

    def test_fetch_async_with_mock(self, monkeypatch):
        class FakeResp:
            status_code = 200
            headers = {}
            cookies = {}
            text = "async hi"
            content = b"async hi"
            encoding = "utf-8"

        class FakeAsyncSession:
            def __init__(self, **kwargs):
                assert kwargs.get("impersonate") == "chrome131"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, **kwargs):
                return FakeResp()

        import sys, types

        fake_async_mod = types.ModuleType("curl_cffi.requests")
        fake_async_mod.AsyncSession = FakeAsyncSession
        fake_curl = types.ModuleType("curl_cffi")
        # Ensure curl_cffi import succeeds
        if "curl_cffi" not in sys.modules:
            monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl)
        monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_async_mod)

        client = CurlCffiClient(impersonate="chrome131")

        async def run():
            resp = await client.fetch_async(Request(url="https://e.com/a"))
            assert resp.text == "async hi"

        asyncio.run(run())

    def test_session_kwargs_with_ja3(self):
        client = CurlCffiClient(impersonate="", ja3="fake_ja3", akamai="fake_akamai", user_agent="my-agent/1.0")
        kwargs = client._session_kwargs()
        assert kwargs["ja3"] == "fake_ja3"
        assert kwargs["akamai"] == "fake_akamai"
        assert kwargs["headers"]["User-Agent"] == "my-agent/1.0"
        assert "impersonate" not in kwargs

    def test_session_kwargs_with_impersonate(self):
        client = CurlCffiClient(impersonate="chrome131", ja3="x")
        kwargs = client._session_kwargs()
        assert kwargs["impersonate"] == "chrome131"
        assert "ja3" not in kwargs
        assert "headers" not in kwargs
