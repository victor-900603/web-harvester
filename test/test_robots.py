from __future__ import annotations

import asyncio

import httpx
import pytest

from src.core.http_client.base import BaseHttpClient
from src.core.request import Request
from src.core.response import Response
from src.core.robots import RobotsPolicy


class FakeClient(BaseHttpClient):
    """HTTP client stub that records robots.txt lookups."""

    def __init__(self, responses=None, exc=None):
        self._responses = responses or {}
        self._exc = exc
        self.requests: list[str] = []

    def _respond(self, request: Request) -> Response:
        self.requests.append(request.url)
        if self._exc is not None:
            raise self._exc
        status, text = self._responses.get(request.url, (404, ""))
        return Response(url=request.url, status_code=status, text=text, request=request)

    def fetch_sync(self, request: Request) -> Response:
        return self._respond(request)

    async def fetch_async(self, request: Request) -> Response:
        return self._respond(request)


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/robots.txt")
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


ALLOW_ALL = "User-agent: *\nAllow: /\n"
DISALLOW_PRIVATE = "User-agent: *\nDisallow: /private/\n"


def make_policy(client, user_agent="web-harvester/1.0"):
    return RobotsPolicy(client, user_agent)


class TestAllowed:
    def test_allowed_when_robots_permits(self):
        client = FakeClient({"https://example.com/robots.txt": (200, ALLOW_ALL)})
        policy = make_policy(client)
        assert policy.allowed("https://example.com/news/1") is True

    def test_disallowed_path_is_rejected(self):
        client = FakeClient({"https://example.com/robots.txt": (200, DISALLOW_PRIVATE)})
        policy = make_policy(client)
        assert policy.allowed("https://example.com/private/1") is False
        assert policy.allowed("https://example.com/news/1") is True

    def test_missing_robots_allows_all(self):
        client = FakeClient()
        policy = make_policy(client)
        assert policy.allowed("https://example.com/news/1") is True
        assert client.requests == ["https://example.com/robots.txt"]

    def test_client_error_allows_all(self):
        client = FakeClient(exc=_status_error(403))
        policy = make_policy(client)
        assert policy.allowed("https://example.com/news/1") is True

    def test_server_error_denies_and_is_cached(self):
        client = FakeClient({"https://example.com/robots.txt": (503, "")})
        policy = make_policy(client)
        assert policy.allowed("https://example.com/a") is False
        assert policy.allowed("https://example.com/b") is False
        assert client.requests == ["https://example.com/robots.txt"]

    def test_transport_error_denies_and_is_cached(self):
        client = FakeClient(exc=httpx.ConnectError("boom"))
        policy = make_policy(client)
        assert policy.allowed("https://example.com/a") is False
        assert policy.allowed("https://example.com/b") is False
        assert client.requests == ["https://example.com/robots.txt"]

    def test_one_fetch_per_origin(self):
        client = FakeClient({"https://example.com/robots.txt": (200, ALLOW_ALL)})
        policy = make_policy(client)
        assert policy.allowed("https://example.com/a") is True
        assert policy.allowed("https://example.com/b") is True
        assert policy.allowed("https://other.test/c") is True
        assert client.requests == [
            "https://example.com/robots.txt",
            "https://other.test/robots.txt",
        ]

    def test_non_http_scheme_is_allowed_without_fetch(self):
        client = FakeClient()
        policy = make_policy(client)
        assert policy.allowed("ftp://example.com/file") is True
        assert client.requests == []

    def test_user_agent_specific_group_wins(self):
        robots = (
            "User-agent: googlebot\n"
            "Disallow: /\n"
            "\n"
            "User-agent: *\n"
            "Allow: /\n"
        )
        client = FakeClient({"https://example.com/robots.txt": (200, robots)})
        policy = make_policy(client)
        assert policy.allowed("https://example.com/news/1") is True

    def test_disallow_logged(self, caplog):
        import logging

        client = FakeClient({"https://example.com/robots.txt": (200, DISALLOW_PRIVATE)})
        policy = make_policy(client)
        with caplog.at_level(logging.INFO, logger="src.core.robots"):
            policy.allowed("https://example.com/private/1")
        assert any("robots.txt disallows" in rec.getMessage() for rec in caplog.records)


class TestAllowedAsync:
    def test_allowed_async_uses_async_fetch(self):
        client = FakeClient({"https://example.com/robots.txt": (200, ALLOW_ALL)})
        policy = make_policy(client)
        assert asyncio.run(policy.allowed_async("https://example.com/news/1")) is True
        assert client.requests == ["https://example.com/robots.txt"]

    def test_disallowed_async(self):
        client = FakeClient({"https://example.com/robots.txt": (200, DISALLOW_PRIVATE)})
        policy = make_policy(client)
        assert asyncio.run(policy.allowed_async("https://example.com/private/1")) is False

    def test_server_error_async_denies_and_is_cached(self):
        client = FakeClient({"https://example.com/robots.txt": (500, "")})
        policy = make_policy(client)
        assert asyncio.run(policy.allowed_async("https://example.com/a")) is False
        assert asyncio.run(policy.allowed_async("https://example.com/b")) is False
        assert client.requests == ["https://example.com/robots.txt"]

    def test_transport_error_async_denies(self):
        client = FakeClient(exc=httpx.ConnectError("boom"))
        policy = make_policy(client)
        assert asyncio.run(policy.allowed_async("https://example.com/a")) is False


@pytest.mark.parametrize("url", ["https://example.com", "https://example.com/x?y=1"])
def test_allow_all_parser_accepts_everything(url):
    client = FakeClient({"https://example.com/robots.txt": (404, "")})
    policy = make_policy(client)
    assert policy.allowed(url) is True
