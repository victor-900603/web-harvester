from __future__ import annotations

from abc import ABC, abstractmethod

from ..request import Request
from ..response import Response


class BaseHttpClient(ABC):
    """Abstract HTTP client used by CrawlerEngine."""

    @abstractmethod
    def fetch_sync(self, request: Request) -> Response:
        """Synchronously fetch a single request."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_async(self, request: Request) -> Response:
        """Asynchronously fetch a single request."""
        raise NotImplementedError

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass
