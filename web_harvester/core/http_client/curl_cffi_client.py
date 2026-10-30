from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..request import Request
from ..response import Response
from .base import BaseHttpClient

logger = logging.getLogger(__name__)

IMPORT_HINT = (
    "curl_cffi is not installed but http_client='curl_cffi' is configured. "
    "Install it with: pip install curl_cffi"
)


class CurlCffiClient(BaseHttpClient):
    """curl_cffi backed client with connection reuse.

    A single :class:`curl_cffi.requests.Session` is created on first use and
    reused for every subsequent request so TCP and TLS fingerprints are
    negotiated once instead of per request. Call :meth:`close` (sync) or
    :meth:`aclose` (async) to release the sessions.
    """

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
        self._session: Optional[Any] = None
        self._async_session: Optional[Any] = None

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
    def _raise_for_status(request: Request, status_code: int, headers: Dict[str, str]) -> None:
        if 200 <= status_code < 300:
            return
        raise httpx.HTTPStatusError(
            f"{status_code} Client Error for url: {request.url}",
            request=httpx.Request(request.method, request.url),
            response=httpx.Response(
                status_code,
                headers=headers,
                request=httpx.Request(request.method, request.url),
            ),
        )

    @staticmethod
    def _cookies_to_dict(cookies: Any) -> Dict[str, str]:
        try:
            if isinstance(cookies, dict):
                return dict(cookies)
            return {k: v for k, v in cookies.items()}
        except Exception:
            return {}

    @staticmethod
    def _headers_to_dict(headers: Any) -> Dict[str, str]:
        try:
            return dict(headers)
        except Exception:
            return {}

    def _build_response(self, request: Request, resp: Any) -> Response:
        self._raise_for_status(request, resp.status_code, dict(resp.headers))
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

    def _get_session(self) -> Any:
        """Return the shared synchronous session, creating it on first use."""
        if self._session is None:
            try:
                from curl_cffi import requests as crequests
            except ImportError as e:
                raise ImportError(IMPORT_HINT) from e
            self._session = crequests.Session(**self._session_kwargs())
        return self._session

    def _get_async_session(self) -> Any:
        """Return the shared asynchronous session, creating it on first use."""
        if self._async_session is None:
            try:
                from curl_cffi.requests import AsyncSession
            except ImportError as e:
                raise ImportError(IMPORT_HINT) from e
            self._async_session = AsyncSession(**self._session_kwargs())
        return self._async_session

    def _request_kwargs(self, request: Request) -> Dict[str, Any]:
        return {
            "method": request.method,
            "url": request.url,
            "headers": request.headers or None,
            "cookies": request.cookies or None,
            "params": request.params or None,
            "data": request.body,
            "json": request.json_body,
            "timeout": request.timeout or self._timeout,
        }

    def fetch_sync(self, request: Request) -> Response:
        session = self._get_session()
        resp = session.request(**self._request_kwargs(request))
        return self._build_response(request, resp)

    async def fetch_async(self, request: Request) -> Response:
        session = self._get_async_session()
        resp = await session.request(**self._request_kwargs(request))
        return self._build_response(request, resp)

    def close(self) -> None:
        """Close the shared synchronous session, if any."""
        session, self._session = self._session, None
        if session is not None:
            session.close()

    async def aclose(self) -> None:
        """Close the shared asynchronous session, if any."""
        session, self._async_session = self._async_session, None
        if session is not None:
            await session.close()
