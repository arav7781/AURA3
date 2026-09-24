"""Web and news search with layered fallbacks.

Web search: DuckDuckGo text API → DuckDuckGo news API → DuckDuckGo Lite HTML page.
If every tier fails the caller is told to rely on the model's own knowledge.
"""

import logging
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("aura.search")

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _ddgs():
    from ddgs import DDGS

    return DDGS(timeout=10)


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Return a list of {title, url, snippet}. Empty list if every tier failed."""
    try:
        hits = _ddgs().text(query, max_results=max_results)
        results = [
            {"title": h.get("title", ""), "url": h.get("href", ""), "snippet": h.get("body", "")}
            for h in hits or []
        ]
        if results:
            logger.info(f"Web search (DuckDuckGo text) → {len(results)} results for: {query[:70]}")
            return results
    except Exception as e:
        logger.warning(f"DuckDuckGo text search failed: {e}")

    try:
        hits = _ddgs().news(query, max_results=max_results)
        results = [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("body", "")}
            for h in hits or []
        ]
        if results:
            logger.info(f"Web search (DuckDuckGo news) → {len(results)} results for: {query[:70]}")
            return results
    except Exception as e:
        logger.warning(f"DuckDuckGo news search failed: {e}")

    try:
        resp = httpx.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={"User-Agent": _UA},
            timeout=10,
        )
        if resp.status_code == 200:
            links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class=.result-link.[^>]*>(.*?)</a>', resp.text)
            snippets = re.findall(r'<td[^>]*class=.result-snippet.[^>]*>(.*?)</td>', resp.text, re.DOTALL)
            results = []
            for i, (url, title) in enumerate(links[:max_results]):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                results.append({"title": re.sub(r"<[^>]+>", "", title).strip(), "url": url, "snippet": snippet})
            if results:
                logger.info(f"Web search (DuckDuckGo Lite) → {len(results)} results for: {query[:70]}")
                return results
    except Exception as e:
        logger.warning(f"DuckDuckGo Lite search failed: {e}")

    logger.warning(f"All web search tiers failed for: {query[:70]}")
    return []


def format_results(results: List[Dict[str, str]], query: str) -> str:
    if not results:
        return (
            f"Web search unavailable for '{query}'. Use pre-trained knowledge and say that "
            "figures are estimates."
        )
    return "\n\n".join(
        f"[{i + 1}] {r['title']}\nURL: {r['url']}\n{r['snippet']}" for i, r in enumerate(results)
    )


def news_search(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """Return RapidAPI-shaped news items from DuckDuckGo News (used when no RapidAPI key)."""
    try:
        hits = _ddgs().news(query, max_results=max_results)
    except Exception as e:
        logger.warning(f"DuckDuckGo news failed for {query}: {e}")
        return []
    return [
        {
            "article_title": h.get("title", ""),
            "article_url": h.get("url", ""),
            "article_photo_url": h.get("image", ""),
            "source": h.get("source", ""),
            "post_time_utc": h.get("date", ""),
            "snippet": h.get("body", ""),
        }
        for h in hits or []
    ]
