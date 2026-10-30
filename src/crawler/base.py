from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generator, Union

from ..core.item import Item
from ..core.request import Request
from ..core.response import Response


class BaseCrawler(ABC):
    name: str = "base"

    @property
    def limits(self) -> dict:
        return {}

    @property
    def respect_robots(self) -> bool | None:
        """Site-level override for ``request.respect_robots``; None uses the global value."""
        return None

    @abstractmethod
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate the initial requests to crawl.

        Yield:
            Request: The initial requests to start the crawling process.
        """
        raise NotImplementedError("start_requests method must be implemented by the subclass.")

    @abstractmethod
    def parse(self, response: Response) -> Generator[Union[Request, Item], None, None]:
        """Parse the response and yield items or new requests.

        Args:
            response (Response): The response to parse.

        Yield:
            Union[Request, Item]: The items or new requests extracted from the response.
        """
        raise NotImplementedError("parse method must be implemented by the subclass.")
