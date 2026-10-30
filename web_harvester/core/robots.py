from __future__ import annotations

import logging
from typing import Dict, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .http_client.base import BaseHttpClient
from .request import Request

logger = logging.getLogger(__name__)


def _origin(url: str) -> Optional[str]:
    """Return ``scheme://host[:port]`` for an absolute HTTP(S) URL, else None."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


class RobotsPolicy:
    """robots.txt lookups with one fetch per origin.

    Decision rules:

    - 4xx: no robots.txt is published, so every path is allowed.
    - 5xx or transport failure: requests to that origin are skipped for the
      current run, because the crawler cannot confirm that access is permitted.
      The failure is remembered for the rest of the run so a broken robots.txt
      is not refetched for every URL.
    - Anything else is parsed with :class:`urllib.robotparser.RobotFileParser`
      and matched against the configured user agent.

    Args:
        http_client (BaseHttpClient): Client used to fetch robots.txt.
        user_agent (str): User agent matched against the robots.txt groups.
    """

    def __init__(self, http_client: BaseHttpClient, user_agent: str):
        self._client = http_client
        self._user_agent = user_agent
        self._parsers: Dict[str, Optional[RobotFileParser]] = {}

    def allowed(self, url: str) -> bool:
        """Return whether ``url`` may be fetched according to robots.txt."""
        origin = _origin(url)
        if origin is None:
            return True
        return self._allows(origin, url, self._load(origin))

    async def allowed_async(self, url: str) -> bool:
        """Asynchronous counterpart of :meth:`allowed`."""
        origin = _origin(url)
        if origin is None:
            return True
        if origin not in self._parsers:
            self._parsers[origin] = await self._load_async(origin)
        return self._allows(origin, url, self._parsers[origin])

    def _allows(self, origin: str, url: str, parser: Optional[RobotFileParser]) -> bool:
        if parser is None:
            logger.debug(f"robots.txt unavailable for {origin}; skipping requests to this origin")
            return False
        allowed = parser.can_fetch(self._user_agent, url)
        if not allowed:
            logger.info(f"robots.txt disallows {url}")
        return allowed

    def _load(self, origin: str) -> Optional[RobotFileParser]:
        if origin in self._parsers:
            return self._parsers[origin]
        robots_url = f"{origin}/robots.txt"
        try:
            response = self._client.fetch_sync(Request(url=robots_url))
        except Exception as exc:
            parser = self._parser_from_error(robots_url, exc)
        else:
            parser = self._parser_from_response(robots_url, response.status_code, response.text)
        self._parsers[origin] = parser
        return parser

    async def _load_async(self, origin: str) -> Optional[RobotFileParser]:
        robots_url = f"{origin}/robots.txt"
        try:
            response = await self._client.fetch_async(Request(url=robots_url))
        except Exception as exc:
            return self._parser_from_error(robots_url, exc)
        return self._parser_from_response(robots_url, response.status_code, response.text)

    def _parser_from_response(
        self, robots_url: str, status_code: int, text: str
    ) -> Optional[RobotFileParser]:
        if 400 <= status_code < 500:
            logger.debug(f"robots.txt not published ({status_code}) at {robots_url}; allowing all paths")
            return self._allow_all()
        if status_code >= 500:
            logger.warning(
                f"robots.txt returned {status_code} at {robots_url}; "
                "skipping requests to this origin for this run"
            )
            return None
        parser = RobotFileParser()
        parser.parse((text or "").splitlines())
        return parser

    def _parser_from_error(self, robots_url: str, exc: BaseException) -> Optional[RobotFileParser]:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status_code, int):
            return self._parser_from_response(robots_url, status_code, "")
        logger.warning(
            f"Failed to fetch {robots_url}: {exc}. "
            "Skipping requests to this origin for this run"
        )
        return None

    @staticmethod
    def _allow_all() -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse([])
        return parser
