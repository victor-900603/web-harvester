from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Request:
    """HTTP request object.

    Attributes:
        url: The URL to send the request to.
        method: The HTTP method to use (e.g., "GET", "POST").
        headers: A dictionary of HTTP headers to include in the request.
        cookies: A dictionary of cookies to include in the request.
        params: A dictionary of query parameters to include in the URL.
        body: The body of the request (for POST, PUT, etc.).
        json_body: A JSON-serializable object to include in the request body.
        meta: A dictionary of arbitrary metadata to associate with the request.
        callback: The name of the callback function to call with the response.
        errback: The name of the error callback function to call if the request fails.
        is_article: Whether the request targets an article page. Dry runs use it
            to skip per-article fetches while still crawling the list pages.
        timeout: Per-request timeout in seconds. The engine sets the remaining
            crawl budget here so a single request cannot outlive the overall
            timeout; None falls back to the client default.
    """

    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Any] = None
    json_body: Optional[Any] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    callback: Optional[str] = None
    errback: Optional[str] = None
    is_article: bool = False
    timeout: Optional[float] = None

    def copy(self) -> Request:
        return Request(
            url=self.url,
            method=self.method,
            headers=self.headers.copy(),
            cookies=self.cookies.copy(),
            params=self.params.copy(),
            body=self.body,
            json_body=self.json_body,
            meta=self.meta.copy(),
            callback=self.callback,
            errback=self.errback,
            is_article=self.is_article,
            timeout=self.timeout,
        )

    def __repr__(self):
        return f"<Request method={self.method} url={self.url}>"
