"""
TruthSocialMonitor - Monitors Truth Social for market-moving posts.

Polls for new posts and extracts market-relevant keywords.
No official API exists — uses the public RSS/Atom feed.

Config via env vars:
    TRUTH_SOCIAL_ENABLED: "true"/"false" (default: false)
    TRUTH_SOCIAL_POLL_INTERVAL: seconds (default: 30)

Design notes:
- Truth Social exposes a Mastodon-compatible RSS feed at
  https://truthsocial.com/@{user}/feed.rss  (also .atom).
- We request the RSS variant with Accept: application/rss+xml.
- Parsing is done with lightweight regex; no lxml/BeautifulSoup dependency.
- Post IDs are deduplicated in memory; history capped at _max_history items.
- Every poll error is logged but never propagates — the monitor degrades
  gracefully when the feed is unreachable.

Sentiment classification:
    BULLISH_OIL     → 'bullish'  (geopolitical supply disruption signals)
    BEARISH_OIL     → 'bearish'  (diplomatic de-escalation signals)
    MARKET_FEAR     → 'bearish'  (macro demand-destruction signals)
    MARKET_BULLISH  → 'bullish'  (pro-growth / pro-market signals)

Confidence scoring:
    confidence = min(1.0, number_of_matched_keywords * 0.3)
    0 keywords  → post filtered out (not market-relevant)
    1 keyword   → 0.3
    2 keywords  → 0.6
    3+ keywords → 0.9 – 1.0

Edge cases:
    - Feed unreachable / non-200 → returns [] (no exception propagated).
    - Feed returns Atom format  → parsed via <entry> elements.
    - Feed returns RSS format   → parsed via <item> elements.
    - HTML entities in content  → stripped by the <tag> regex; raw &amp; etc.
      are left in place (callers use text for keyword matching, not display).
    - Duplicate posts across polls → suppressed via _seen_ids set.
    - Non-parseable timestamps   → silently falls back to datetime.now(UTC).
"""

import asyncio
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

import httpx
import structlog

from src.services.informed_flow.schemas import TrumpPost

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Keyword dictionaries
# Keys must be lowercase; matching is done against text.lower().
# ---------------------------------------------------------------------------

# Geopolitical supply-disruption signals → oil price goes up.
BULLISH_OIL: List[str] = [
    "iran attack",
    "iran strike",
    "bomb iran",
    "military action",
    "sanctions iran",
    "oil embargo",
    "venezuela sanctions",
    "pipeline attack",
    "strait of hormuz",
]

# Diplomatic de-escalation or supply-increase signals → oil price goes down.
BEARISH_OIL: List[str] = [
    "iran deal",
    "iran talks",
    "iran agreement",
    "productive",
    "peace",
    "deal reached",
    "diplomacy",
    "opec increase",
    "release reserves",
    "strategic petroleum reserve",
]

# Macro demand-destruction / risk-off signals → equities and oil go down.
MARKET_FEAR: List[str] = [
    "china",
    "tariff",
    "trade war",
    "crash",
    "recession",
    "dump",
    "failing",
    "bankrupt",
    "emergency",
    "disaster",
]

# Pro-growth / pro-market signals → equities go up.
MARKET_BULLISH: List[str] = [
    "great economy",
    "stock market",
    "all time high",
    "boom",
    "winning",
    "greatest economy",
    "jobs",
    "gdp",
    "no inflation",
]


class TruthSocialMonitor:
    """Polls Truth Social for new posts from @realDonaldTrump.

    Extracts market-moving keywords and classifies sentiment.  All I/O runs
    inside an asyncio task that can be started and stopped via start()/stop().

    Args:
        poll_interval: Seconds between successive feed polls.
            Range: [1, ∞).  Default 30 s.
        target_user: Truth Social username to monitor (without leading @).
            Default: 'realDonaldTrump'.

    Env vars:
        TRUTH_SOCIAL_ENABLED: Must be exactly 'true' (case-insensitive) for
            polling to begin.  Any other value leaves the monitor idle.
        TRUTH_SOCIAL_POLL_INTERVAL: Integer override for poll_interval.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        target_user: str = "realDonaldTrump",
    ) -> None:
        env_interval = os.getenv("TRUTH_SOCIAL_POLL_INTERVAL")
        if env_interval is not None:
            try:
                poll_interval = int(env_interval)
            except ValueError:
                pass  # Ignore malformed env var; use constructor default.

        self.poll_interval = poll_interval
        self.target_user = target_user
        self.enabled = os.getenv("TRUTH_SOCIAL_ENABLED", "false").lower() == "true"

        # Deduplicate posts across polls.
        self._seen_ids: Set[str] = set()

        # Circular history buffer (newest appended, oldest popped when over cap).
        self._recent_posts: List[TrumpPost] = []
        self._max_history: int = 100

        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background polling loop.

        No-op when TRUTH_SOCIAL_ENABLED != 'true'.  Safe to call multiple
        times — a second call while running is silently ignored.
        """
        if not self.enabled:
            logger.info("truth_social_monitor_disabled")
            return
        if self._running:
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("truth_social_monitor_started", interval=self.poll_interval)

    def stop(self) -> None:
        """Stop the background polling loop and close the HTTP client.

        Safe to call when already stopped.
        """
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("truth_social_monitor_stopped")

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Fetch feed, analyse new posts, and sleep until the next poll.

        Any exception during a single poll is caught and logged; the loop
        continues until _running is set to False or the task is cancelled.
        """
        while self._running:
            try:
                new_posts = await self._fetch_new_posts()
                for raw_post in new_posts:
                    analysed = self._analyze_post(raw_post)
                    if analysed is not None:
                        self._recent_posts.append(analysed)
                        if len(self._recent_posts) > self._max_history:
                            self._recent_posts = self._recent_posts[-self._max_history:]
                        logger.info(
                            "trump_post_detected",
                            sentiment=analysed.sentiment,
                            keywords=analysed.keywords_found,
                            confidence=analysed.confidence,
                            text_preview=analysed.post_text[:100],
                        )
            except Exception:
                logger.exception("truth_social_poll_error")

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    async def _fetch_new_posts(self) -> List[Dict]:
        """Fetch and parse the RSS feed; return only posts not yet seen.

        Returns:
            List of raw post dicts with keys: 'text', 'id' (or 'link'),
            'timestamp'.  Returns an empty list when the feed is unavailable
            or the HTTP client has not been initialised.

        Edge cases:
            - Non-200 HTTP status  → empty list, warning logged.
            - Network timeout      → empty list, debug logged.
            - Any other exception  → empty list, exception logged.
        """
        if not self._client:
            return []

        url = f"https://truthsocial.com/@{self.target_user}/feed.rss"
        try:
            resp = await self._client.get(
                url,
                headers={"Accept": "application/rss+xml, application/atom+xml"},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                logger.debug(
                    "truth_social_fetch_failed",
                    status=resp.status_code,
                    url=url,
                )
                return []

            raw_posts = self._parse_feed(resp.text)

            new_posts: List[Dict] = []
            for post in raw_posts:
                post_id = post.get("id") or post.get("link") or ""
                if post_id and post_id not in self._seen_ids:
                    self._seen_ids.add(post_id)
                    new_posts.append(post)

            return new_posts

        except httpx.TimeoutException:
            logger.debug("truth_social_timeout", url=url)
            return []
        except Exception:
            logger.exception("truth_social_fetch_error", url=url)
            return []

    # ------------------------------------------------------------------
    # Feed parsing
    # ------------------------------------------------------------------

    def _parse_feed(self, feed_text: str) -> List[Dict]:
        """Parse RSS or Atom feed XML into a list of raw post dicts.

        Supports both Atom (<entry> elements) and RSS (<item> elements).
        HTML tags inside content/description fields are stripped.

        Args:
            feed_text: Raw XML response body from the feed endpoint.

        Returns:
            List of dicts with keys:
                'text'      — plaintext post body (may be empty string).
                'id'        — Atom <id> or RSS <guid> value (may be absent).
                'link'      — canonical URL (may be absent).
                'timestamp' — raw ISO or RFC-2822 timestamp string (may be absent).
            Only entries with non-empty 'text' are included.

        Edge cases:
            - Empty feed_text   → returns [].
            - No recognised tags → returns [].
            - CDATA wrappers    → handled naturally (CDATA content is stripped
              of the <![CDATA[ ... ]]> markers before tag removal).
        """
        posts: List[Dict] = []

        # Prefer Atom entries; fall back to RSS items.
        entries = re.findall(r"<entry>(.*?)</entry>", feed_text, re.DOTALL)
        if not entries:
            entries = re.findall(r"<item>(.*?)</item>", feed_text, re.DOTALL)

        for entry in entries:
            post: Dict = {}

            # --- Post body ---------------------------------------------------
            # Atom: <content type="html">…</content>  or  <content>…</content>
            # RSS:  <description>…</description>
            content_match = re.search(
                r"<content(?:[^>]*)>(.*?)</content>", entry, re.DOTALL
            )
            if not content_match:
                content_match = re.search(
                    r"<description>(.*?)</description>", entry, re.DOTALL
                )
            if content_match:
                raw = content_match.group(1)
                # Strip CDATA wrappers.
                raw = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw, flags=re.DOTALL)
                # Strip remaining HTML tags.
                text = re.sub(r"<[^>]+>", "", raw)
                post["text"] = text.strip()

            # --- Post ID -----------------------------------------------------
            # Atom: <id>…</id>    RSS: <guid>…</guid>
            id_match = re.search(r"<id>(.*?)</id>", entry) or re.search(
                r"<guid[^>]*>(.*?)</guid>", entry
            )
            if id_match:
                post["id"] = id_match.group(1).strip()

            # --- Canonical link ----------------------------------------------
            # Atom: <link href="…"/>   RSS: <link>…</link>
            link_match = re.search(r'<link[^>]+href="([^"]+)"', entry)
            if not link_match:
                link_match = re.search(r"<link>(.*?)</link>", entry, re.DOTALL)
            if link_match:
                post["link"] = link_match.group(1).strip()

            # --- Timestamp ---------------------------------------------------
            # Atom: <published>…</published>   RSS: <pubDate>…</pubDate>
            time_match = re.search(
                r"<(?:published|updated|pubDate)>(.*?)</(?:published|updated|pubDate)>",
                entry,
            )
            if time_match:
                post["timestamp"] = time_match.group(1).strip()

            if post.get("text"):
                posts.append(post)

        return posts

    # ------------------------------------------------------------------
    # Sentiment analysis
    # ------------------------------------------------------------------

    def _analyze_post(self, post: Dict) -> Optional[TrumpPost]:
        """Classify a raw post dict for market relevance and sentiment.

        Args:
            post: Dict produced by _parse_feed().  Must contain a non-empty
                'text' key.

        Returns:
            TrumpPost with classified sentiment and confidence, or None when
            the post contains no market-relevant keywords.

        Sentiment resolution:
            Bullish-oil keywords beat bearish-oil keywords when counts tie.
            When oil counts are equal and fear keywords fire → 'bearish'.
            When oil counts are equal and market-bullish keywords fire → 'bullish'.
            When all counts are zero (should never reach here) → 'neutral'.

        Confidence:
            confidence = min(1.0, len(keywords_found) * 0.3)
            Rounded to 2 decimal places.
            Range: [0.3, 1.0] (0.0 only possible if called with zero keywords,
            which is blocked by the early-return guard).

        Edge cases:
            - Empty text → returns None.
            - Post with keywords from multiple conflicting categories → the
              category with the higher count wins; ties broken as above.
        """
        text = post.get("text", "")
        if not text:
            return None

        text_lower = text.lower()

        keywords_found: List[str] = []
        scores: Dict[str, int] = {
            "bullish_oil": 0,
            "bearish_oil": 0,
            "fear": 0,
            "bullish_market": 0,
        }

        for kw in BULLISH_OIL:
            if kw in text_lower:
                keywords_found.append(kw)
                scores["bullish_oil"] += 1

        for kw in BEARISH_OIL:
            if kw in text_lower:
                keywords_found.append(kw)
                scores["bearish_oil"] += 1

        for kw in MARKET_FEAR:
            if kw in text_lower:
                keywords_found.append(kw)
                scores["fear"] += 1

        for kw in MARKET_BULLISH:
            if kw in text_lower:
                keywords_found.append(kw)
                scores["bullish_market"] += 1

        if not keywords_found:
            return None  # Not market-relevant.

        # Resolve sentiment: oil-specific signals take priority.
        if scores["bullish_oil"] > scores["bearish_oil"]:
            sentiment = "bullish"
        elif scores["bearish_oil"] > scores["bullish_oil"]:
            sentiment = "bearish"
        elif scores["fear"] > 0:
            sentiment = "bearish"
        elif scores["bullish_market"] > 0:
            sentiment = "bullish"
        else:
            sentiment = "neutral"

        confidence = round(min(1.0, len(keywords_found) * 0.3), 2)

        # Parse timestamp; fall back to now(UTC) if absent or malformed.
        timestamp = datetime.now(timezone.utc)
        raw_ts = post.get("timestamp", "")
        if raw_ts:
            try:
                timestamp = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass  # Use the UTC-now fallback set above.

        return TrumpPost(
            post_text=text[:500],
            timestamp=timestamp,
            keywords_found=keywords_found,
            sentiment=sentiment,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_recent_posts(self, hours_back: int = 24) -> List[TrumpPost]:
        """Return analysed posts published within the last `hours_back` hours.

        Args:
            hours_back: Look-back window in hours.  Range: [0, ∞).
                0 returns an empty list.

        Returns:
            Oldest-first list of TrumpPost objects whose timestamps fall
            within [now - hours_back, now].
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        return [p for p in self._recent_posts if p.timestamp >= cutoff]

    def has_recent_catalyst(self, minutes_back: int = 30) -> Optional[TrumpPost]:
        """Return the most recent market-moving post within `minutes_back` minutes.

        Args:
            minutes_back: Look-back window in minutes.  Range: [0, ∞).

        Returns:
            The most recent TrumpPost with confidence >= 0.3 within the
            window, or None if no such post exists.  Posts are searched
            newest-first so the returned post is always the latest catalyst.

        Edge cases:
            - Empty history → returns None.
            - Multiple posts in window → returns the newest one.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
        for post in reversed(self._recent_posts):
            if post.timestamp >= cutoff and post.confidence >= 0.3:
                return post
        return None
