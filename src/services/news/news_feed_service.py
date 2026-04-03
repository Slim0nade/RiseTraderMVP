"""
NewsFeedService - Aggregates market news from free APIs.

Provides news context for informed flow detection.
Primary: NewsAPI.org, Fallback: Finnhub.

Inputs:
    NEWSAPI_KEY env var: API key for newsapi.org (optional; skipped if absent).
    FINNHUB_API_KEY env var: API key for finnhub.io (optional; skipped if absent).

Outputs:
    List[NewsItem] sorted newest-first, deduplicated by headline.
    NewsItem.relevance_score: 0.7 for NewsAPI results, 0.6 for Finnhub results
        (providers do not supply per-article relevance; these are tier constants).

Cache:
    Results are cached per-symbol for _cache_ttl seconds (default 300 s).
    Cache key is the symbol string.  Stale cache entries are replaced on the
    next fetch for that symbol.

Edge cases:
    - Missing API keys: that provider is skipped silently.
    - HTTP errors: logged as warnings; empty list returned for that provider.
    - Malformed article datetimes: fall back to datetime.now(UTC).
    - No articles match relevance filter (Finnhub): returns [].
    - Both providers down: get_recent_news returns [].
"""

import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
import structlog

from src.services.informed_flow.schemas import NewsItem

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Symbol → query string mapping
# ---------------------------------------------------------------------------

# Maps MT4 symbol names to natural-language search queries used for NewsAPI
# and keyword filtering for Finnhub.  Each query uses OR-separated terms so
# that either name variant matches.
SYMBOL_QUERIES: dict[str, str] = {
    "CrudeOIL": "crude oil OR WTI OR petroleum",
    "BRENT_OIL": "brent oil OR brent crude",
    "USA500": "S&P 500 OR stock market",
    "XAUUSD": "gold price OR gold futures",
    "GBPJPY": "GBPJPY OR pound yen",
    "CORN": "corn futures OR corn price",
    "WHEAT": "wheat futures OR wheat price",
}


class NewsFeedService:
    """
    Fetches recent market news from free-tier APIs.

    Tries NewsAPI.org first; falls back to Finnhub if NewsAPI returns no
    articles or is not configured.

    Args:
        cache_ttl: Seconds to cache results per symbol.  Default 300 (5 min).
            Set to 0 to disable caching entirely.

    Config via env vars:
        NEWSAPI_KEY: API key for newsapi.org.
        FINNHUB_API_KEY: API key for finnhub.io.
    """

    def __init__(self, cache_ttl: int = 300) -> None:
        self.newsapi_key: str = os.getenv("NEWSAPI_KEY", "")
        self.finnhub_key: str = os.getenv("FINNHUB_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None
        # symbol -> (cache_timestamp, List[NewsItem])
        self._cache: dict[str, tuple[datetime, List[NewsItem]]] = {}
        self._cache_ttl: int = cache_ttl

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Return the shared async HTTP client, creating it on first call.

        Returns:
            An httpx.AsyncClient with a 10-second timeout.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        """
        Close the underlying HTTP client and release resources.

        Safe to call multiple times.
        """
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_recent_news(
        self,
        symbols: List[str],
        lookback_minutes: int = 30,
    ) -> List[NewsItem]:
        """
        Fetch recent news for the given symbols.

        Tries NewsAPI first, falls back to Finnhub.  Results are cached per
        symbol for _cache_ttl seconds.

        Args:
            symbols: List of MT4 symbol strings (e.g. ['CrudeOIL', 'XAUUSD']).
                Unknown symbols fall back to using the raw symbol name as the
                query term.
            lookback_minutes: How far back to search for articles.
                Must be >= 1.  Default 30.

        Returns:
            Deduplicated list of NewsItem sorted newest-first.
            Deduplication is by exact headline string.
            Returns [] when both providers are unconfigured or unavailable.

        Edge cases:
            - Duplicate headline from two sources: only the first occurrence
              is kept (NewsAPI result takes precedence over Finnhub).
            - lookback_minutes=0 or negative: treated as 1 minute.
        """
        effective_lookback = max(1, lookback_minutes)
        all_news: List[NewsItem] = []

        for symbol in symbols:
            cached = self._cache.get(symbol)
            if cached and self._cache_ttl > 0:
                cache_time, cache_items = cached
                age = (datetime.now(timezone.utc) - cache_time).total_seconds()
                if age < self._cache_ttl:
                    all_news.extend(cache_items)
                    continue

            items = await self._fetch_for_symbol(symbol, effective_lookback)
            self._cache[symbol] = (datetime.now(timezone.utc), items)
            all_news.extend(items)

        # Deduplicate by exact headline, preserving insertion order (NewsAPI
        # results appear before Finnhub because we append in symbol order and
        # NewsAPI is tried first).
        seen: set[str] = set()
        unique: List[NewsItem] = []
        for item in all_news:
            if item.headline not in seen:
                seen.add(item.headline)
                unique.append(item)

        # Sort newest-first.
        unique.sort(key=lambda x: x.published_at, reverse=True)
        return unique

    async def has_catalyst(
        self,
        symbol: str,
        timestamp: Optional[datetime] = None,
        window_minutes: int = 30,
    ) -> bool:
        """
        Check whether a news catalyst exists for the symbol near a given time.

        Args:
            symbol: MT4 symbol string (e.g. 'CrudeOIL').
            timestamp: Reference time (default: now UTC).  Currently unused for
                filtering — the lookback window is applied relative to the
                current wall-clock time.  Provided for API symmetry with the
                InformedFlowDetector interface.
            window_minutes: How far back to search.  Default 30.

        Returns:
            True if at least one news article was found within the window.
            False when no articles exist or both providers are unavailable.
        """
        news = await self.get_recent_news([symbol], lookback_minutes=window_minutes)
        return len(news) > 0

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    async def _fetch_for_symbol(
        self, symbol: str, lookback_minutes: int
    ) -> List[NewsItem]:
        """
        Fetch news for a single symbol, trying providers in priority order.

        Args:
            symbol: MT4 symbol string.
            lookback_minutes: Look-back window in minutes (>= 1 guaranteed by caller).

        Returns:
            List of NewsItem from the first provider that returns results.
            Empty list when both providers fail or are unconfigured.
        """
        if self.newsapi_key:
            try:
                items = await self._fetch_newsapi(symbol, lookback_minutes)
                if items:
                    return items
            except Exception:
                logger.exception("newsapi_fetch_failed", symbol=symbol)

        if self.finnhub_key:
            try:
                items = await self._fetch_finnhub(symbol, lookback_minutes)
                if items:
                    return items
            except Exception:
                logger.exception("finnhub_fetch_failed", symbol=symbol)

        return []

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _fetch_newsapi(
        self, symbol: str, lookback_minutes: int
    ) -> List[NewsItem]:
        """
        Fetch from NewsAPI.org /v2/everything endpoint.

        Args:
            symbol: MT4 symbol string used to build the search query.
            lookback_minutes: How far back to search (applied as the `from`
                parameter in UTC).

        Returns:
            List of NewsItem with relevance_score=0.7 (NewsAPI tier constant).
            Empty list on HTTP error or empty response.

        Edge cases:
            - HTTP status != 200: logs warning, returns [].
            - Missing article fields: falls back to empty string / now().
        """
        query = SYMBOL_QUERIES.get(symbol, symbol)
        from_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

        client = await self._get_client()
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "sortBy": "publishedAt",
                "pageSize": 10,
                "apiKey": self.newsapi_key,
            },
        )

        if resp.status_code != 200:
            logger.warning(
                "newsapi_error",
                symbol=symbol,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return []

        data = resp.json()
        items: List[NewsItem] = []
        for article in data.get("articles", []):
            published = _parse_iso_datetime(article.get("publishedAt", ""))
            items.append(
                NewsItem(
                    headline=article.get("title", ""),
                    source=article.get("source", {}).get("name", "unknown"),
                    published_at=published,
                    # NewsAPI does not provide a relevance score; 0.7 is the
                    # tier constant indicating a high-quality primary source.
                    relevance_score=0.7,
                    url=article.get("url", ""),
                )
            )

        return items

    async def _fetch_finnhub(
        self, symbol: str, lookback_minutes: int
    ) -> List[NewsItem]:
        """
        Fetch from Finnhub /api/v1/news endpoint.

        Finnhub's free-tier general news endpoint returns a flat list of recent
        articles without symbol filtering.  This method filters the response
        by checking whether any term from SYMBOL_QUERIES appears in the
        headline (case-insensitive).

        Args:
            symbol: MT4 symbol string used to derive filter terms.
            lookback_minutes: Articles older than this window are discarded.

        Returns:
            List of NewsItem with relevance_score=0.6 (Finnhub tier constant).
            Empty list on HTTP error or no matching articles.

        Edge cases:
            - HTTP status != 200: logs warning, returns [].
            - Non-list response: treated as empty.
            - article["datetime"] missing or 0: falls back to now().
            - article["datetime"] is a Unix timestamp (int).
        """
        from_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

        client = await self._get_client()
        resp = await client.get(
            "https://finnhub.io/api/v1/news",
            params={
                "category": "general",
                "minId": 0,
                "token": self.finnhub_key,
            },
        )

        if resp.status_code != 200:
            logger.warning(
                "finnhub_error",
                symbol=symbol,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return []

        data = resp.json()
        if not isinstance(data, list):
            return []

        # Build the filter set from the query string for this symbol.
        raw_query = SYMBOL_QUERIES.get(symbol, symbol)
        filter_terms = [t.strip().lower() for t in raw_query.split(" OR ")]

        items: List[NewsItem] = []
        for article in data:
            headline = article.get("headline", "")
            headline_lower = headline.lower()

            # Require at least one query term in the headline.
            if not any(term in headline_lower for term in filter_terms):
                continue

            published = _parse_unix_timestamp(article.get("datetime", 0))

            # Discard articles outside the requested window.
            if published < from_time:
                continue

            items.append(
                NewsItem(
                    headline=headline,
                    source=article.get("source", "unknown"),
                    published_at=published,
                    # Finnhub does not provide a relevance score; 0.6 is the
                    # tier constant indicating a secondary/fallback source.
                    relevance_score=0.6,
                    url=article.get("url", ""),
                )
            )

        return items


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_iso_datetime(value: str) -> datetime:
    """
    Parse an ISO 8601 datetime string to a timezone-aware UTC datetime.

    Args:
        value: ISO 8601 string (e.g. '2024-01-15T12:00:00Z').

    Returns:
        Timezone-aware UTC datetime.  Falls back to datetime.now(UTC) on any
        parse error, so callers never receive a naive datetime.
    """
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _parse_unix_timestamp(value: object) -> datetime:
    """
    Convert a Unix timestamp (int or float) to a timezone-aware UTC datetime.

    Args:
        value: Unix timestamp.  0, None, or any non-numeric value falls back
            to datetime.now(UTC).

    Returns:
        Timezone-aware UTC datetime.  Falls back to datetime.now(UTC) on any
        conversion error or when value <= 0.
    """
    try:
        ts = float(value)  # type: ignore[arg-type]
        if ts <= 0:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc)
