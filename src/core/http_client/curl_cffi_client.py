from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from .base import BaseHttpClient
from ..request import Request
from ..response import Response

logger = logging.getLogger(__name__)


class CurlCffiClient(BaseHttpClient):
    def __init__(
        self,
        timeout: float = 30,
        verify_ssl: bool = True,
        user_agent: str = "web-harvester/1.0",
        impersonate: str = "chrome131",
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
    ) -> None:
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._user_agent = user_agent
        self._impersonate: Optional[str] = impersonate if impersonate != "" else None
        self._ja3 = ja3
        self._akamai = akamai

        if self._impersonate and (ja3 or akamai):
            logger.warning(
                "impersonate='%s' is set; ja3/akamai values will be ignored because "
                "browser impersonation already defines the TLS fingerprint.",
                self._impersonate,
            )

    def _session_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "verify": self._verify_ssl,
            "timeout": self._timeout,
        }
        if self._impersonate:
            kwargs["impersonate"] = self._impersonate
        else:
            kwargs["headers"] = {"User-Agent": self._user_agent}
            if self._ja3:
                kwargs["ja3"] = self._ja3
            if self._akamai:
                kwargs["akamai"] = self._akamai
        return kwargs

    @staticmethod
    def _raise_for_status(request: Request, status_code: int, headers: Dict[str, str], text: str) -> None:
        if 200 <= status_code < 300:
            return
        raise httpx.HTTPStatusError(
            f"{status_code} Client Error for url: {request.url}",
            request=httpx.Request(request.method, request.url),
            response=httpx.Response(status_code, request=httpx.Request(request.method, request.url)),
        )

    @staticmethod
    def _cookies_to_dict(cookies: Any) -> Dict[str, str]:
        try:
            if isinstance(cookies, dict):
                return dict(cookies)
            return {k: v for k, v in cookies.items()}  # type: ignore[union-attr]
        except Exception:
            return {}

    @staticmethod
    def _headers_to_dict(headers: Any) -> Dict[str, str]:
        try:
            if isinstance(headers, dict):
                return dict(headers)
            return dict(headers)
        except Exception:
            return {}

    def fetch_sync(self, request: Request) -> Response:
        try:
            from curl_cffi import requests as crequests
        except ImportError as e:
            raise ImportError(
                "curl_cffi is not installed but http_client='curl_cffi' is configured. "
                "Install it with: pip install curl_cffi"
            ) from e

        session_kwargs = self._session_kwargs()
        with crequests.Session(**session_kwargs) as session:
            resp = session.request(
                method=request.method,
                url=request.url,
                headers=request.headers or None,
                cookies=request.cookies or None,
                params=request.params or None,
                data=request.body,
                json=request.json_body,
                timeout=self._timeout,
            )
            self._raise_for_status(request, resp.status_code, dict(resp.headers), resp.text)

            headers = self._headers_to_dict(resp.headers)
            cookies = self._cookies_to_dict(getattr(resp, "cookies", {}))
            encoding = getattr(resp, "encoding", None) or "utf-8"
            text = resp.text if isinstance(resp.text, str) else resp.content.decode(encoding, errors="replace") if resp.content else ""
            body = resp.content if hasattr(resp, "content") else text.encode(encoding)

            return Response(
                url=request.url,
                status_code=resp.status_code,
                headers=headers,
                cookies=cookies,
                text=text,
                body=body,
                request=request,
                encoding=encoding,
            )

    async def fetch_async(self, request: Request) -> Response:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError as e:
            raise ImportError(
                "curl_cffi is not installed but http_client='curl_cffi' is configured. "
                "Install it with: pip install curl_cffi"
            ) from e

        session_kwargs = self._session_kwargs()
        async with AsyncSession(**session_kwargs) as session:
            resp = await session.request(
                method=request.method,
                url=request.url,
                headers=request.headers or None,
                cookies=request.cookies or None,
                params=request.params or None,
                data=request.body,
                json=request.json_body,
                timeout=self._timeout,
            )
            self._raise_for_status(request, resp.status_code, dict(resp.headers), resp.text)

            headers = self._headers_to_dict(resp.headers)
            cookies = self._cookies_to_dict(getattr(resp, "cookies", {}))
            encoding = getattr(resp, "encoding", None) or "utf-8"
            text = resp.text if isinstance(resp.text, str) else resp.content.decode(encoding, errors="replace") if resp.content else ""
            body = resp.content if hasattr(resp, "content") else text.encode(encoding)

            return Response(
                url=request.url,
                status_code=resp.status_code,
                headers=headers,
                cookies=cookies,
                text=text,
                body=body,
                request=request,
                encoding=encoding,
            )
