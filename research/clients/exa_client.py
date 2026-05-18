"""Exa API client for the Exa search agent (deep search + highlights)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import Settings
from ..schemas import SourceSnippet

logger = logging.getLogger(__name__)


class ExaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _search_sync(self, query: str) -> tuple[list[SourceSnippet], str]:
        try:
            from exa_py import Exa
        except ImportError as exc:  # pragma: no cover
            raise ImportError("exa-py is required. Install with: pip install exa-py") from exc

        exa = Exa(api_key=self._settings.exa_search_api_key)
        response = exa.search(
            query,
            type=self._settings.exa_search_type,
            num_results=self._settings.exa_num_results,
            contents={"highlights": True},
        )

        snippets: list[SourceSnippet] = []
        for result in getattr(response, "results", None) or []:
            url = getattr(result, "url", "") or ""
            title = getattr(result, "title", "") or ""
            excerpt = _result_excerpt(result)
            if url:
                snippets.append(SourceSnippet(url=url, title=title, excerpt=excerpt))

        summary_parts: list[str] = []
        output = getattr(response, "output", None)
        if output is not None:
            content = getattr(output, "content", None)
            if content:
                if isinstance(content, str):
                    summary_parts.append(content)
                else:
                    summary_parts.append(str(content))

        if not summary_parts and snippets:
            summary_parts.append(
                f"Found {len(snippets)} sources for query: {query!r}",
            )

        return snippets, "\n\n".join(summary_parts) if summary_parts else ""

    async def search(self, query: str) -> tuple[list[SourceSnippet], str]:
        return await asyncio.to_thread(self._search_sync, query)


def _result_excerpt(result: Any) -> str:
    highlights = getattr(result, "highlights", None)
    if highlights:
        if isinstance(highlights, list):
            return " ".join(str(h) for h in highlights[:8])
        return str(highlights)
    text = getattr(result, "text", None)
    if text:
        return str(text)[:8000]
    return getattr(result, "snippet", "") or ""
