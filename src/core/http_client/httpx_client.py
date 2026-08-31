from __future__ import annotations

import httpx

from .base import BaseHttpClient
from ..request import Request
from ..response import Response


class HttpxClient(BaseHttpClient):
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

    def fetch_sync(self, request: Request) -> Response:
        with httpx.Client(
            timeout=self._timeout,
            verify=self._verify_ssl,
            headers={"User-Agent": self._user_agent},
        ) as client:
            resp = client.request(
                method=request.method,
                url=request.url,
                headers=request.headers or None,
                cookies=request.cookies or None,
                params=request.params or None,
                data=request.body,
                json=request.json_body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return self._build_response(request, resp)

    async def fetch_async(self, request: Request) -> Response:
        limits = httpx.Limits(
            max_connections=self._max_concurrency,
            max_keepalive_connections=self._max_concurrency,
        )
        timeout_cfg = httpx.Timeout(self._timeout)
        async with httpx.AsyncClient(
            timeout=timeout_cfg,
            limits=limits,
            verify=self._verify_ssl,
            headers={"User-Agent": self._user_agent},
        ) as client:
            resp = await client.request(
                method=request.method,
                url=request.url,
                headers=request.headers or None,
                cookies=request.cookies or None,
                params=request.params or None,
                data=request.body,
                json=request.json_body,
            )
            resp.raise_for_status()
            return self._build_response(request, resp)
