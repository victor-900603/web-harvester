from __future__ import annotations

from typing import Optional

import httpx

from ..request import Request
from ..response import Response
from .base import BaseHttpClient


class HttpxClient(BaseHttpClient):
    """httpx backed client with connection pooling.

    One :class:`httpx.Client` and one :class:`httpx.AsyncClient` are created
    lazily and reused, so keep-alive connections survive between requests.
    Call :meth:`close` (sync) or :meth:`aclose` (async) to release them.
    """

    def __init__(
        self,
        timeout: float = 30,
        verify_ssl: bool = True,
        user_agent: str = "web-harvester/1.0",
        max_concurrency: int = 10,
    ) -> None:
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._user_agent = user_agent
        self._max_concurrency = max_concurrency
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    def _build_response(self, request: Request, httpx_resp: httpx.Response) -> Response:
        return Response(
            url=request.url,
            status_code=httpx_resp.status_code,
            headers=dict(httpx_resp.headers),
            cookies=dict(httpx_resp.cookies),
            text=httpx_resp.text,
            body=httpx_resp.content,
            request=request,
            encoding=httpx_resp.encoding or "utf-8",
        )

    def _get_client(self) -> httpx.Client:
        """Return the shared synchronous client, creating it on first use."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                verify=self._verify_ssl,
                headers={"User-Agent": self._user_agent},
            )
        return self._client

    def _get_async_client(self) -> httpx.AsyncClient:
        """Return the shared asynchronous client, creating it on first use."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(
                    max_connections=self._max_concurrency,
                    max_keepalive_connections=self._max_concurrency,
                ),
                verify=self._verify_ssl,
                headers={"User-Agent": self._user_agent},
            )
        return self._async_client

    @staticmethod
    def _request_kwargs(request: Request) -> dict:
        return {
            "method": request.method,
            "url": request.url,
            "headers": request.headers or None,
            "cookies": request.cookies or None,
            "params": request.params or None,
            "data": request.body,
            "json": request.json_body,
        }

    def fetch_sync(self, request: Request) -> Response:
        client = self._get_client()
        resp = client.request(
            **self._request_kwargs(request),
            timeout=request.timeout or self._timeout,
        )
        resp.raise_for_status()
        return self._build_response(request, resp)

    async def fetch_async(self, request: Request) -> Response:
        client = self._get_async_client()
        resp = await client.request(
            **self._request_kwargs(request),
            timeout=request.timeout or self._timeout,
        )
        resp.raise_for_status()
        return self._build_response(request, resp)

    def close(self) -> None:
        """Close the shared synchronous client, if any."""
        client, self._client = self._client, None
        if client is not None:
            client.close()

    async def aclose(self) -> None:
        """Close the shared asynchronous client, if any."""
        client, self._async_client = self._async_client, None
        if client is not None:
            await client.aclose()
