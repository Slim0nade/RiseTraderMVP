"""
Unit tests for NewsFeedService.

Tests processing and filtering logic only — no real HTTP calls are made.
httpx.AsyncClient is mocked at the boundary (this is a unit test; the
no-mock rule applies to MT4/MCP/database interactions only).

Coverage:
    T1  SYMBOL_QUERIES mapping contains all expected symbols.
    T2  Deduplication by headline: same headline from two sources kept once.
    T3  Cache TTL: cached results returned within 5 minutes, no re-fetch.
    T4  Cache bypass: results are re-fetched after TTL expires.
    T5  has_catalyst returns True when news exists.
    T6  has_catalyst returns False when no articles are returned.
    T7  NewsAPI HTTP error returns empty list (no crash).
    T8  Finnhub HTTP error returns empty list (no crash).
    T9  NewsAPI results are sorted newest-first.
    T10 Finnhub articles outside the lookback window are discarded.
    T11 Finnhub articles not matching any query term are discarded.
    T12 NewsAPI missing keys fall back to empty strings / now().
    T13 Finnhub non-list response returns empty list.
    T14 _parse_iso_datetime handles Z suffix and bad input.
    T15 _parse_unix_timestamp handles zero, negative, and bad input.
    T16 cache_ttl=0 disables caching (always re-fetches).
    T17 NewsAPI tried first; Finnhub used only when NewsAPI returns nothing.
    T18 Neither provider configured returns empty list.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.news.news_feed_service import (
    NewsFeedService,
    SYMBOL_QUERIES,
    _parse_iso_datetime,
    _parse_unix_timestamp,
)
from src.services.informed_flow.schemas import NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_data: object) -> MagicMock:
    """Build a mock httpx.Response with the given status and JSON payload."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = ""
    return resp


def _newsapi_article(
    title: str = "WTI crude falls",
    source_name: str = "Reuters",
    published_at: str = "2024-01-15T12:00:00Z",
    url: str = "https://example.com/1",
) -> dict:
    """Return a minimal NewsAPI article dict."""
    return {
        "title": title,
        "source": {"name": source_name},
        "publishedAt": published_at,
        "url": url,
    }


def _finnhub_article(
    headline: str = "crude oil prices drop",
    source: str = "MarketWatch",
    dt: int = 1705320000,  # 2024-01-15T12:00:00Z
    url: str = "https://example.com/2",
) -> dict:
    """Return a minimal Finnhub article dict."""
    return {
        "headline": headline,
        "source": source,
        "datetime": dt,
        "url": url,
    }


def _future_unix(minutes: int = 0) -> int:
    """Unix timestamp for `minutes` from now (default: now)."""
    return int((datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp())


async def _run(coro):
    """Run a coroutine in the test event loop."""
    return await coro


# ---------------------------------------------------------------------------
# T1: SYMBOL_QUERIES mapping
# ---------------------------------------------------------------------------

class TestSymbolQueries:
    """SYMBOL_QUERIES must cover every instrument in the platform."""

    EXPECTED_SYMBOLS = {
        "CrudeOIL",
        "BRENT_OIL",
        "USA500",
        "XAUUSD",
        "GBPJPY",
        "CORN",
        "WHEAT",
    }

    def test_all_expected_symbols_present(self):
        missing = self.EXPECTED_SYMBOLS - set(SYMBOL_QUERIES.keys())
        assert not missing, f"Missing symbols in SYMBOL_QUERIES: {missing}"

    def test_no_empty_query_strings(self):
        for sym, query in SYMBOL_QUERIES.items():
            assert query.strip(), f"Empty query for symbol '{sym}'"

    def test_all_queries_contain_or_separator(self):
        """Every query must have at least one OR to ensure broad coverage."""
        for sym, query in SYMBOL_QUERIES.items():
            assert " OR " in query, (
                f"Query for '{sym}' has no OR terms: '{query}'"
            )


# ---------------------------------------------------------------------------
# T2: Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Same headline from two different sources must appear only once."""

    @pytest.mark.asyncio
    async def test_same_headline_deduplicated(self):
        """
        Arrange: NewsAPI returns article A; cache is then bypassed and Finnhub
        returns the same headline.  Inject both sets directly via mocked
        _fetch_for_symbol to exercise the deduplication path without HTTP.
        """
        svc = NewsFeedService(cache_ttl=0)

        now = datetime.now(timezone.utc)
        item_a = NewsItem(
            headline="Crude oil surges on supply cuts",
            source="Reuters",
            published_at=now,
            relevance_score=0.7,
            url="https://a.com/1",
        )
        item_b = NewsItem(
            headline="Crude oil surges on supply cuts",  # duplicate headline
            source="Bloomberg",
            published_at=now - timedelta(minutes=1),
            relevance_score=0.6,
            url="https://b.com/1",
        )

        # Inject two items with the same headline for the same symbol.
        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            return [item_a, item_b]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        result = await svc.get_recent_news(["CrudeOIL"])
        headlines = [r.headline for r in result]
        assert headlines.count("Crude oil surges on supply cuts") == 1

    @pytest.mark.asyncio
    async def test_different_headlines_both_kept(self):
        """Two articles with different headlines must both appear in the result."""
        svc = NewsFeedService(cache_ttl=0)
        now = datetime.now(timezone.utc)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            return [
                NewsItem("Headline A", "Reuters", now, 0.7, "https://a.com/1"),
                NewsItem("Headline B", "Reuters", now - timedelta(seconds=30), 0.7, "https://a.com/2"),
            ]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        result = await svc.get_recent_news(["CrudeOIL"])
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_multi_symbol_deduplication(self):
        """
        Same headline returned for two different symbols must appear only once
        in the merged result.
        """
        svc = NewsFeedService(cache_ttl=0)
        now = datetime.now(timezone.utc)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            # Both symbols return the same headline.
            return [NewsItem("Oil and gold move together", "CNBC", now, 0.7, "https://x.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        result = await svc.get_recent_news(["CrudeOIL", "XAUUSD"])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# T3 & T4: Cache TTL
# ---------------------------------------------------------------------------

class TestCacheTTL:
    """Cache hit prevents re-fetch within TTL; cache miss triggers re-fetch."""

    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl(self):
        """
        After the first fetch, a second call within the TTL window must NOT
        invoke _fetch_for_symbol again.
        """
        svc = NewsFeedService(cache_ttl=300)  # 5-minute TTL
        now = datetime.now(timezone.utc)
        call_count = 0

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            nonlocal call_count
            call_count += 1
            return [NewsItem("Some news", "Reuters", now, 0.7, "https://x.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        # First call — populates cache.
        await svc.get_recent_news(["CrudeOIL"])
        # Second call — should hit cache.
        await svc.get_recent_news(["CrudeOIL"])

        assert call_count == 1, (
            f"Expected 1 fetch (cache hit on second call), got {call_count}"
        )

    @pytest.mark.asyncio
    async def test_cache_returns_same_items(self):
        """Cached results must be identical to the original fetch result."""
        svc = NewsFeedService(cache_ttl=300)
        now = datetime.now(timezone.utc)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            return [NewsItem("Fresh news", "Bloomberg", now, 0.7, "https://b.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        first = await svc.get_recent_news(["CrudeOIL"])
        second = await svc.get_recent_news(["CrudeOIL"])

        assert first[0].headline == second[0].headline

    @pytest.mark.asyncio
    async def test_cache_miss_after_ttl_expiry(self):
        """
        Manually backdate the cache timestamp to simulate TTL expiry; the
        next call must invoke _fetch_for_symbol again.
        """
        svc = NewsFeedService(cache_ttl=300)
        now = datetime.now(timezone.utc)
        call_count = 0

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            nonlocal call_count
            call_count += 1
            return [NewsItem("News item", "Reuters", now, 0.7, "https://r.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        # Populate cache.
        await svc.get_recent_news(["CrudeOIL"])

        # Expire the cache by backdating the stored timestamp.
        stale_time = now - timedelta(seconds=svc._cache_ttl + 1)
        svc._cache["CrudeOIL"] = (stale_time, svc._cache["CrudeOIL"][1])

        # Should trigger a re-fetch.
        await svc.get_recent_news(["CrudeOIL"])

        assert call_count == 2, (
            f"Expected 2 fetches (re-fetch after TTL), got {call_count}"
        )

    @pytest.mark.asyncio
    async def test_cache_disabled_when_ttl_zero(self):
        """cache_ttl=0 must always re-fetch (T16)."""
        svc = NewsFeedService(cache_ttl=0)
        now = datetime.now(timezone.utc)
        call_count = 0

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            nonlocal call_count
            call_count += 1
            return [NewsItem("Item", "Reuters", now, 0.7, "https://r.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        await svc.get_recent_news(["CrudeOIL"])
        await svc.get_recent_news(["CrudeOIL"])

        assert call_count == 2, (
            f"cache_ttl=0 must disable caching; expected 2 fetches, got {call_count}"
        )


# ---------------------------------------------------------------------------
# T5 & T6: has_catalyst
# ---------------------------------------------------------------------------

class TestHasCatalyst:
    """has_catalyst returns True when news exists, False when empty."""

    @pytest.mark.asyncio
    async def test_returns_true_when_news_exists(self):
        svc = NewsFeedService(cache_ttl=0)
        now = datetime.now(timezone.utc)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            return [NewsItem("Oil news", "Reuters", now, 0.7, "https://x.com")]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        assert await svc.has_catalyst("CrudeOIL") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_news(self):
        svc = NewsFeedService(cache_ttl=0)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            return []

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        assert await svc.has_catalyst("CrudeOIL") is False

    @pytest.mark.asyncio
    async def test_uses_window_minutes_parameter(self):
        """has_catalyst must pass window_minutes down to get_recent_news."""
        svc = NewsFeedService(cache_ttl=0)
        received_lookback = None

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            nonlocal received_lookback
            received_lookback = lookback_minutes
            return []

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        await svc.has_catalyst("CrudeOIL", window_minutes=60)

        assert received_lookback == 60


# ---------------------------------------------------------------------------
# T7 & T8: HTTP error handling
# ---------------------------------------------------------------------------

class TestHTTPErrors:
    """HTTP errors from either provider must return an empty list, not crash."""

    @pytest.mark.asyncio
    async def test_newsapi_http_error_returns_empty(self):
        """NewsAPI 401/429/500 must log a warning and return []."""
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "test_key"
        svc.finnhub_key = ""  # disable Finnhub for isolation

        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(401, {"message": "unauthorized"})
        svc._client = mock_client

        result = await svc._fetch_newsapi("CrudeOIL", 30)
        assert result == []

    @pytest.mark.asyncio
    async def test_finnhub_http_error_returns_empty(self):
        """Finnhub 403/500 must log a warning and return []."""
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = ""
        svc.finnhub_key = "test_key"

        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(403, {"error": "forbidden"})
        svc._client = mock_client

        result = await svc._fetch_finnhub("CrudeOIL", 30)
        assert result == []


# ---------------------------------------------------------------------------
# T9: Sort order
# ---------------------------------------------------------------------------

class TestSortOrder:
    """Results must be sorted newest-first."""

    @pytest.mark.asyncio
    async def test_results_sorted_newest_first(self):
        svc = NewsFeedService(cache_ttl=0)
        older = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        newer = datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc)

        async def fake_fetch(symbol: str, lookback_minutes: int) -> List[NewsItem]:
            # Return older item first deliberately.
            return [
                NewsItem("Older headline", "Reuters", older, 0.7, "https://a.com"),
                NewsItem("Newer headline", "Reuters", newer, 0.7, "https://b.com"),
            ]

        svc._fetch_for_symbol = fake_fetch  # type: ignore[method-assign]

        result = await svc.get_recent_news(["CrudeOIL"])
        assert result[0].published_at >= result[1].published_at


# ---------------------------------------------------------------------------
# T10: Finnhub time window filtering
# ---------------------------------------------------------------------------

class TestFinnhubTimeFilter:
    """Articles outside the lookback window must be discarded by _fetch_finnhub."""

    @pytest.mark.asyncio
    async def test_old_article_discarded(self):
        """
        An article published 2 hours ago must be discarded when lookback is 30 min.
        """
        svc = NewsFeedService(cache_ttl=0)
        svc.finnhub_key = "test_key"

        two_hours_ago = _future_unix(minutes=-120)
        five_minutes_ago = _future_unix(minutes=-5)

        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, [
            _finnhub_article(
                headline="crude oil old news",
                dt=two_hours_ago,
            ),
            _finnhub_article(
                headline="crude oil recent news",
                dt=five_minutes_ago,
            ),
        ])
        svc._client = mock_client

        result = await svc._fetch_finnhub("CrudeOIL", lookback_minutes=30)

        headlines = [r.headline for r in result]
        assert "crude oil old news" not in headlines
        assert "crude oil recent news" in headlines


# ---------------------------------------------------------------------------
# T11: Finnhub relevance filtering
# ---------------------------------------------------------------------------

class TestFinnhubRelevanceFilter:
    """Finnhub articles that don't match any query term must be discarded."""

    @pytest.mark.asyncio
    async def test_irrelevant_article_discarded(self):
        """
        An article about 'tech stocks' must not appear in CrudeOIL results.
        """
        svc = NewsFeedService(cache_ttl=0)
        svc.finnhub_key = "test_key"

        now_ts = _future_unix(minutes=-5)

        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, [
            _finnhub_article(headline="Tech stocks rally on AI news", dt=now_ts),
            _finnhub_article(headline="WTI crude climbs 2% on OPEC news", dt=now_ts),
        ])
        svc._client = mock_client

        result = await svc._fetch_finnhub("CrudeOIL", lookback_minutes=30)

        headlines = [r.headline for r in result]
        assert "Tech stocks rally on AI news" not in headlines
        assert "WTI crude climbs 2% on OPEC news" in headlines

    @pytest.mark.asyncio
    async def test_relevance_score_is_finnhub_tier_constant(self):
        """Finnhub items must carry relevance_score == 0.6."""
        svc = NewsFeedService(cache_ttl=0)
        svc.finnhub_key = "test_key"

        now_ts = _future_unix(minutes=-5)
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, [
            _finnhub_article(headline="crude oil rises", dt=now_ts),
        ])
        svc._client = mock_client

        result = await svc._fetch_finnhub("CrudeOIL", lookback_minutes=30)

        assert len(result) == 1
        assert result[0].relevance_score == 0.6


# ---------------------------------------------------------------------------
# T12: NewsAPI missing fields
# ---------------------------------------------------------------------------

class TestNewsAPIFallbacks:
    """Missing fields in NewsAPI response must fall back to safe defaults."""

    @pytest.mark.asyncio
    async def test_missing_title_falls_back_to_empty_string(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "test_key"

        article = {"source": {"name": "Reuters"}, "publishedAt": "2024-01-15T12:00:00Z", "url": "https://x.com"}
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, {"articles": [article]})
        svc._client = mock_client

        result = await svc._fetch_newsapi("CrudeOIL", 30)
        assert result[0].headline == ""

    @pytest.mark.asyncio
    async def test_missing_source_name_falls_back_to_unknown(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "test_key"

        article = {"title": "Oil news", "source": {}, "publishedAt": "2024-01-15T12:00:00Z", "url": ""}
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, {"articles": [article]})
        svc._client = mock_client

        result = await svc._fetch_newsapi("CrudeOIL", 30)
        assert result[0].source == "unknown"

    @pytest.mark.asyncio
    async def test_relevance_score_is_newsapi_tier_constant(self):
        """NewsAPI items must carry relevance_score == 0.7."""
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "test_key"

        article = _newsapi_article()
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, {"articles": [article]})
        svc._client = mock_client

        result = await svc._fetch_newsapi("CrudeOIL", 30)
        assert result[0].relevance_score == 0.7


# ---------------------------------------------------------------------------
# T13: Finnhub non-list response
# ---------------------------------------------------------------------------

class TestFinnhubNonListResponse:
    """Finnhub returning a dict (e.g. an error object) must return []."""

    @pytest.mark.asyncio
    async def test_dict_response_returns_empty(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.finnhub_key = "test_key"

        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(200, {"error": "rate limit"})
        svc._client = mock_client

        result = await svc._fetch_finnhub("CrudeOIL", 30)
        assert result == []


# ---------------------------------------------------------------------------
# T14: _parse_iso_datetime
# ---------------------------------------------------------------------------

class TestParseIsoDatetime:
    """_parse_iso_datetime must handle Z suffix and bad input gracefully."""

    def test_valid_z_suffix(self):
        dt = _parse_iso_datetime("2024-01-15T12:00:00Z")
        assert dt.tzinfo is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 12

    def test_valid_offset(self):
        dt = _parse_iso_datetime("2024-01-15T12:00:00+00:00")
        assert dt.tzinfo is not None
        assert dt.hour == 12

    def test_empty_string_returns_now(self):
        before = datetime.now(timezone.utc)
        dt = _parse_iso_datetime("")
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_garbage_string_returns_now(self):
        before = datetime.now(timezone.utc)
        dt = _parse_iso_datetime("not-a-date")
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_result_is_timezone_aware(self):
        dt = _parse_iso_datetime("2024-06-01T08:30:00Z")
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# T15: _parse_unix_timestamp
# ---------------------------------------------------------------------------

class TestParseUnixTimestamp:
    """_parse_unix_timestamp must handle zero, negative, and non-numeric input."""

    def test_valid_timestamp(self):
        ts = 1705320000  # 2024-01-15T12:00:00Z
        dt = _parse_unix_timestamp(ts)
        assert dt.tzinfo is not None
        assert dt.year == 2024
        assert dt.month == 1

    def test_zero_returns_now(self):
        before = datetime.now(timezone.utc)
        dt = _parse_unix_timestamp(0)
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_negative_returns_now(self):
        before = datetime.now(timezone.utc)
        dt = _parse_unix_timestamp(-1)
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_none_returns_now(self):
        before = datetime.now(timezone.utc)
        dt = _parse_unix_timestamp(None)
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_string_number_is_parsed(self):
        """Numeric string should parse correctly."""
        dt = _parse_unix_timestamp("1705320000")
        assert dt.year == 2024

    def test_result_is_timezone_aware(self):
        dt = _parse_unix_timestamp(1705320000)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# T17: Provider priority — NewsAPI first, Finnhub only when NewsAPI empty
# ---------------------------------------------------------------------------

class TestProviderPriority:
    """NewsAPI must be tried first; Finnhub is fallback."""

    @pytest.mark.asyncio
    async def test_newsapi_used_first_when_key_set(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "key_a"
        svc.finnhub_key = "key_b"

        newsapi_called = False
        finnhub_called = False

        async def fake_newsapi(symbol, lookback):
            nonlocal newsapi_called
            newsapi_called = True
            now = datetime.now(timezone.utc)
            return [NewsItem("NewsAPI result", "Reuters", now, 0.7, "https://n.com")]

        async def fake_finnhub(symbol, lookback):
            nonlocal finnhub_called
            finnhub_called = True
            return []

        svc._fetch_newsapi = fake_newsapi  # type: ignore[method-assign]
        svc._fetch_finnhub = fake_finnhub  # type: ignore[method-assign]

        await svc._fetch_for_symbol("CrudeOIL", 30)

        assert newsapi_called, "NewsAPI must be called when key is set"
        assert not finnhub_called, (
            "Finnhub must NOT be called when NewsAPI returns results"
        )

    @pytest.mark.asyncio
    async def test_finnhub_used_when_newsapi_returns_empty(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = "key_a"
        svc.finnhub_key = "key_b"

        finnhub_called = False

        async def fake_newsapi(symbol, lookback):
            return []  # NewsAPI returns nothing

        async def fake_finnhub(symbol, lookback):
            nonlocal finnhub_called
            finnhub_called = True
            now = datetime.now(timezone.utc)
            return [NewsItem("Finnhub result", "MW", now, 0.6, "https://f.com")]

        svc._fetch_newsapi = fake_newsapi  # type: ignore[method-assign]
        svc._fetch_finnhub = fake_finnhub  # type: ignore[method-assign]

        await svc._fetch_for_symbol("CrudeOIL", 30)

        assert finnhub_called, "Finnhub must be called when NewsAPI returns nothing"

    @pytest.mark.asyncio
    async def test_newsapi_skipped_when_no_key(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = ""  # no key
        svc.finnhub_key = "key_b"

        newsapi_called = False
        finnhub_called = False

        async def fake_newsapi(symbol, lookback):
            nonlocal newsapi_called
            newsapi_called = True
            return []

        async def fake_finnhub(symbol, lookback):
            nonlocal finnhub_called
            finnhub_called = True
            return []

        svc._fetch_newsapi = fake_newsapi  # type: ignore[method-assign]
        svc._fetch_finnhub = fake_finnhub  # type: ignore[method-assign]

        await svc._fetch_for_symbol("CrudeOIL", 30)

        assert not newsapi_called, "NewsAPI must be skipped when key is absent"
        assert finnhub_called, "Finnhub must be tried as fallback"


# ---------------------------------------------------------------------------
# T18: No provider configured
# ---------------------------------------------------------------------------

class TestNoProviderConfigured:
    """When neither key is set, get_recent_news must return []."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_keys(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = ""
        svc.finnhub_key = ""

        result = await svc.get_recent_news(["CrudeOIL", "XAUUSD"])
        assert result == []

    @pytest.mark.asyncio
    async def test_has_catalyst_returns_false_when_no_keys(self):
        svc = NewsFeedService(cache_ttl=0)
        svc.newsapi_key = ""
        svc.finnhub_key = ""

        assert await svc.has_catalyst("CrudeOIL") is False
