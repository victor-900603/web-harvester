from __future__ import annotations

import logging
from typing import Any

from .base import BaseHttpClient
from .constants import SUPPORTED_HTTP_CLIENTS
from .curl_cffi_client import CurlCffiClient
from .httpx_client import HttpxClient

logger = logging.getLogger(__name__)


def _settings_get(settings: Any, key: str, default: Any = None) -> Any:
    """Dot-aware get that works for both Settings and plain dict."""
    if hasattr(settings, "get"):
        try:
            result = settings.get(key, default)  # type: ignore[call-arg]
            if isinstance(settings, dict) and "." in key and result is default:
                parts = key.split(".")
                cur: Any = settings
                for part in parts:
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        return default
                return cur if cur is not None else default
            return result
        except TypeError:
            pass
    if isinstance(settings, dict):
        parts = key.split(".")
        cur: Any = settings
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur if cur is not None else default
    return default


def build_http_client(settings: Any) -> BaseHttpClient:
    """Factory: build the configured HTTP client from Settings/dict.

    Precedence: settings.get("request.http_client") else "curl_cffi" default.
    Falls back to HttpxClient if curl_cffi is unavailable and http_client is curl_cffi
    (with a warning) to avoid hard crash on environments without the wheel.
    """
    get = lambda k, d=None: _settings_get(settings, k, d)

    http_client_name = get("request.http_client", "curl_cffi") or "curl_cffi"
    timeout = get("request.timeout", None)
    if timeout is None:
        timeout = get("engine.request_timeout", 30)
    verify_ssl = get("request.verify_ssl", True)
    user_agent = get("request.user_agent", "web-harvester/1.0")
    impersonate = get("request.impersonate", "chrome131")
    ja3 = get("request.ja3", None)
    akamai = get("request.akamai", None)
    max_concurrency = get("engine.max_concurrency", 10)

    if http_client_name not in SUPPORTED_HTTP_CLIENTS:
        raise ValueError(f"Unsupported http_client '{http_client_name}'. Supported: {SUPPORTED_HTTP_CLIENTS}")

    if http_client_name == "curl_cffi":
        try:
            import curl_cffi  # noqa: F401  # check availability
            return CurlCffiClient(
                timeout=timeout,
                verify_ssl=verify_ssl,
                user_agent=user_agent,
                impersonate=impersonate if impersonate is not None else "chrome131",
                ja3=ja3,
                akamai=akamai,
            )
        except ImportError:
            logger.warning(
                "curl_cffi not available but http_client='curl_cffi' is configured; "
                "falling back to httpx (TLS fingerprint impersonation disabled)."
            )
            return HttpxClient(
                timeout=timeout,
                verify_ssl=verify_ssl,
                user_agent=user_agent,
                max_concurrency=max_concurrency,
            )

    return HttpxClient(
        timeout=timeout,
        verify_ssl=verify_ssl,
        user_agent=user_agent,
        max_concurrency=max_concurrency,
    )
