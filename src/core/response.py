from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .request import Request

import json as json_lib

@dataclass
class Response:
    """HTTP response object.

    Attributes:
        url: The URL of the response.
        status_code: The HTTP status code of the response.
        headers: A dictionary of HTTP headers in the response.
        request: The Request object that generated this response (if available).
        body: The body of the response.
        encoding: The encoding of the response body (e.g., "utf-8").
    """
    
    url: str
    status_code: int
    text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    request: Optional[Request] = None
    body: Optional[Any] = None
    encoding: str = "utf-8"
    
    @property
    def ok(self) -> bool:
        """Returns True if the response status code is in the 200-299 range."""
        return 200 <= self.status_code < 300
    
    @property
    def content(self) -> Optional[bytes]:
        """Returns the response body as bytes, encoding it if necessary."""
        return self.text.encode(self.encoding) if self.text else None
    
    @property
    def meta(self) -> Optional[Dict[str, Any]]:
        """Returns the meta dictionary from the associated request, if available."""
        return self.request.meta if self.request else None
    
    def json(self) -> Union[Dict[str, Any], List[Any], None]:
        """Parses the response body as JSON and returns the resulting object."""
        if self.body is None:
            return None
        return json_lib.loads(self.body)
    
    def __repr__(self):
        return f"<Response status_code={self.status_code} url={self.url}>"