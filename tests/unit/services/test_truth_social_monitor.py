"""
Unit tests for TruthSocialMonitor.

Pure keyword-analysis and feed-parsing validation only.
No network calls, no mocks of MT4/MCP/database.

Test coverage:
  T1  _analyze_post with bullish-oil keywords returns sentiment='bullish'.
  T2  _analyze_post with bearish-oil keywords returns sentiment='bearish'.
  T3  _analyze_post with market-fear keywords returns sentiment='bearish'.
  T4  _analyze_post with market-bullish keywords returns sentiment='bullish'.
  T5  _analyze_post returns None for a post with no market-relevant keywords.
  T6  _analyze_post returns None for an empty post dict.
  T7  Confidence scales with keyword count and is capped at 1.0.
  T8  _parse_feed correctly parses an RSS feed with one item.
  T9  _parse_feed correctly parses an Atom feed with one entry.
  T10 _parse_feed returns [] for empty / unrecognised input.
  T11 get_recent_posts filters by timestamp window correctly.
  T12 get_recent_posts with hours_back=0 returns empty list.
  T13 has_recent_catalyst returns the newest qualifying post.
  T14 has_recent_catalyst returns None when no posts are within the window.
  T15 Conflicting bullish/bearish counts resolve to the higher count.
  T16 When bullish and bearish counts tie, fear keyword breaks the tie.
  T17 post_text is truncated to 500 characters.
  T18 _parse_feed strips HTML tags from content.
  T19 _parse_feed handles CDATA wrappers.
"""

from datetime import datetime, timezone, timedelta

import pytest

from src.services.social.truth_social_monitor import TruthSocialMonitor
from src.services.informed_flow.schemas import TrumpPost


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def monitor() -> TruthSocialMonitor:
    """Disabled monitor instance — no background task, no network."""
    return TruthSocialMonitor(poll_interval=30, target_user="realDonaldTrump")


def _make_post(text: str, post_id: str = "id-1") -> dict:
    """Helper: build a minimal raw post dict as _parse_feed would return."""
    return {
        "text": text,
        "id": post_id,
        "timestamp": "2026-03-26T12:00:00Z",
    }


# ---------------------------------------------------------------------------
# T1: Bullish oil keywords → sentiment='bullish'
# ---------------------------------------------------------------------------


def test_analyze_post_bullish_oil(monitor):
    """Post mentioning an Iran attack must return bullish sentiment."""
    post = _make_post("We must consider military action against Iran now.")
    result = monitor._analyze_post(post)

    assert result is not None, "Expected TrumpPost but got None"
    assert result.sentiment == "bullish", (
        f"Expected 'bullish', got '{result.sentiment}'"
    )
    assert any("iran" in kw or "military" in kw for kw in result.keywords_found), (
        f"Expected an Iran/military keyword in {result.keywords_found}"
    )


def test_analyze_post_bullish_oil_sanctions(monitor):
    """Post mentioning 'sanctions iran' must return bullish sentiment."""
    post = _make_post("We are imposing the strongest sanctions iran has ever seen!")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bullish"
    assert "sanctions iran" in result.keywords_found


# ---------------------------------------------------------------------------
# T2: Bearish oil keywords → sentiment='bearish'
# ---------------------------------------------------------------------------


def test_analyze_post_bearish_oil(monitor):
    """Post mentioning an Iran deal must return bearish sentiment."""
    post = _make_post("Great news — iran deal has been reached. Diplomacy wins.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bearish", (
        f"Expected 'bearish', got '{result.sentiment}'"
    )


def test_analyze_post_bearish_oil_release_reserves(monitor):
    """Post about releasing strategic petroleum reserve must be bearish oil."""
    post = _make_post(
        "We are releasing strategic petroleum reserve to lower gas prices immediately."
    )
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bearish"
    assert "strategic petroleum reserve" in result.keywords_found


# ---------------------------------------------------------------------------
# T3: Market-fear keywords → sentiment='bearish'
# ---------------------------------------------------------------------------


def test_analyze_post_market_fear_tariff(monitor):
    """Post mentioning tariffs must return bearish sentiment."""
    post = _make_post("China tariff now 200%! Trade war has begun.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bearish", (
        f"Expected 'bearish', got '{result.sentiment}'"
    )
    assert any(kw in result.keywords_found for kw in ("china", "tariff", "trade war")), (
        f"Expected fear keywords in {result.keywords_found}"
    )


def test_analyze_post_market_fear_recession(monitor):
    """Post containing 'recession' and 'crash' must be bearish."""
    post = _make_post("The recession is coming. This could crash everything.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bearish"


# ---------------------------------------------------------------------------
# T4: Market-bullish keywords → sentiment='bullish'
# ---------------------------------------------------------------------------


def test_analyze_post_market_bullish(monitor):
    """Post mentioning all-time stock market high must return bullish."""
    post = _make_post("The stock market has hit an all time high! Best economy ever.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bullish", (
        f"Expected 'bullish', got '{result.sentiment}'"
    )


def test_analyze_post_market_bullish_gdp(monitor):
    """Post about GDP growth must return bullish sentiment."""
    post = _make_post("GDP growth is booming. Winning like never before!")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bullish"


# ---------------------------------------------------------------------------
# T5: Non-market post → None
# ---------------------------------------------------------------------------


def test_analyze_post_returns_none_for_non_market_post(monitor):
    """A post with no market keywords must return None."""
    post = _make_post(
        "Happy birthday to my beautiful granddaughter! What a great day at Mar-a-Lago."
    )
    result = monitor._analyze_post(post)

    assert result is None, f"Expected None but got TrumpPost: {result}"


def test_analyze_post_returns_none_for_golf_post(monitor):
    """A sports/golf post with no financial keywords must return None."""
    post = _make_post(
        "Just played 18 holes at Trump National. Shot a 68. Amazing course!"
    )
    result = monitor._analyze_post(post)

    assert result is None


# ---------------------------------------------------------------------------
# T6: Empty post dict → None
# ---------------------------------------------------------------------------


def test_analyze_post_returns_none_for_empty_text(monitor):
    """A post with empty text must return None."""
    result = monitor._analyze_post({"text": "", "id": "x"})
    assert result is None


def test_analyze_post_returns_none_for_missing_text(monitor):
    """A post dict with no 'text' key must return None."""
    result = monitor._analyze_post({"id": "x", "timestamp": "2026-01-01T00:00:00Z"})
    assert result is None


# ---------------------------------------------------------------------------
# T7: Confidence scales with keyword count, capped at 1.0
# ---------------------------------------------------------------------------


def test_confidence_single_keyword(monitor):
    """One keyword → confidence = 0.30."""
    post = _make_post("iran deal just signed.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.confidence == pytest.approx(0.30, abs=0.01), (
        f"Expected 0.3, got {result.confidence}"
    )


def test_confidence_two_keywords(monitor):
    """Two distinct keywords → confidence = 0.60."""
    # 'iran deal' (bearish_oil) + 'diplomacy' (bearish_oil) = 2 matches
    post = _make_post("The iran deal was reached through skilled diplomacy.")
    result = monitor._analyze_post(post)

    assert result is not None
    assert len(result.keywords_found) == 2, (
        f"Expected 2 keywords, got {result.keywords_found}"
    )
    assert result.confidence == pytest.approx(0.60, abs=0.01)


def test_confidence_capped_at_one(monitor):
    """Many keywords must not push confidence above 1.0."""
    post = _make_post(
        "iran attack military action sanctions iran oil embargo strait of hormuz "
        "pipeline attack venezuela sanctions iran strike bomb iran"
    )
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.confidence <= 1.0, f"Confidence exceeded 1.0: {result.confidence}"
    assert result.confidence == 1.0, (
        f"With 9+ keywords confidence should be 1.0, got {result.confidence}"
    )


# ---------------------------------------------------------------------------
# T8: _parse_feed parses RSS feed
# ---------------------------------------------------------------------------

_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>realDonaldTrump on Truth Social</title>
    <item>
      <guid>https://truthsocial.com/@realDonaldTrump/posts/12345</guid>
      <link>https://truthsocial.com/@realDonaldTrump/posts/12345</link>
      <description>Iran deal reached. Peace at last!</description>
      <pubDate>Wed, 26 Mar 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
      <guid>https://truthsocial.com/@realDonaldTrump/posts/12346</guid>
      <link>https://truthsocial.com/@realDonaldTrump/posts/12346</link>
      <description>Happy birthday to my dog.</description>
      <pubDate>Wed, 26 Mar 2026 11:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def test_parse_feed_rss(monitor):
    """_parse_feed must return both items from a two-item RSS feed."""
    posts = monitor._parse_feed(_RSS_SAMPLE)

    assert len(posts) == 2, f"Expected 2 posts, got {len(posts)}"
    assert posts[0]["text"] == "Iran deal reached. Peace at last!"
    assert posts[0]["id"] == "https://truthsocial.com/@realDonaldTrump/posts/12345"
    assert "12:00:00" in posts[0]["timestamp"]


def test_parse_feed_rss_link_extracted(monitor):
    """_parse_feed must populate the 'link' key from <link> element."""
    posts = monitor._parse_feed(_RSS_SAMPLE)
    assert "link" in posts[0], "Expected 'link' key in parsed post"
    assert "12345" in posts[0]["link"]


# ---------------------------------------------------------------------------
# T9: _parse_feed parses Atom feed
# ---------------------------------------------------------------------------

_ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>realDonaldTrump</title>
  <entry>
    <id>https://truthsocial.com/@realDonaldTrump/posts/99001</id>
    <link href="https://truthsocial.com/@realDonaldTrump/posts/99001"/>
    <content type="html">Sanctions iran will begin immediately!</content>
    <published>2026-03-26T10:00:00Z</published>
  </entry>
</feed>"""


def test_parse_feed_atom(monitor):
    """_parse_feed must correctly parse a single Atom entry."""
    posts = monitor._parse_feed(_ATOM_SAMPLE)

    assert len(posts) == 1, f"Expected 1 post, got {len(posts)}"
    assert posts[0]["text"] == "Sanctions iran will begin immediately!"
    assert posts[0]["id"] == "https://truthsocial.com/@realDonaldTrump/posts/99001"
    assert posts[0]["timestamp"] == "2026-03-26T10:00:00Z"


# ---------------------------------------------------------------------------
# T10: _parse_feed returns [] for empty or unrecognised input
# ---------------------------------------------------------------------------


def test_parse_feed_empty_string(monitor):
    """Empty feed text must return an empty list."""
    assert monitor._parse_feed("") == []


def test_parse_feed_no_items(monitor):
    """Feed with no <entry> or <item> elements must return an empty list."""
    assert monitor._parse_feed("<rss><channel></channel></rss>") == []


def test_parse_feed_garbage_input(monitor):
    """Arbitrary non-XML text must return an empty list, not raise."""
    assert monitor._parse_feed("not xml at all !!!") == []


# ---------------------------------------------------------------------------
# T11: get_recent_posts filters by timestamp window
# ---------------------------------------------------------------------------


def _inject_posts(monitor: TruthSocialMonitor, posts: list) -> None:
    """Directly populate _recent_posts without going through the poll loop."""
    monitor._recent_posts.extend(posts)


def test_get_recent_posts_within_window(monitor):
    """Posts within the look-back window must be returned."""
    now = datetime.now(timezone.utc)
    post = TrumpPost(
        post_text="iran deal reached",
        timestamp=now - timedelta(hours=2),
        keywords_found=["iran deal"],
        sentiment="bearish",
        confidence=0.3,
    )
    _inject_posts(monitor, [post])

    results = monitor.get_recent_posts(hours_back=24)
    assert len(results) == 1
    assert results[0].post_text == "iran deal reached"


def test_get_recent_posts_outside_window_excluded(monitor):
    """Posts older than hours_back must not be returned."""
    now = datetime.now(timezone.utc)
    old_post = TrumpPost(
        post_text="iran attack last week",
        timestamp=now - timedelta(hours=48),
        keywords_found=["iran attack"],
        sentiment="bullish",
        confidence=0.3,
    )
    _inject_posts(monitor, [old_post])

    results = monitor.get_recent_posts(hours_back=24)
    assert len(results) == 0, f"Expected 0 posts, got {len(results)}"


def test_get_recent_posts_mixed_window(monitor):
    """Only posts within the window must be returned when history is mixed."""
    now = datetime.now(timezone.utc)
    recent = TrumpPost(
        post_text="tariff on china",
        timestamp=now - timedelta(hours=1),
        keywords_found=["tariff", "china"],
        sentiment="bearish",
        confidence=0.6,
    )
    old = TrumpPost(
        post_text="oil embargo announced",
        timestamp=now - timedelta(hours=30),
        keywords_found=["oil embargo"],
        sentiment="bullish",
        confidence=0.3,
    )
    _inject_posts(monitor, [old, recent])

    results = monitor.get_recent_posts(hours_back=24)
    assert len(results) == 1
    assert results[0].post_text == "tariff on china"


# ---------------------------------------------------------------------------
# T12: get_recent_posts with hours_back=0 returns empty list
# ---------------------------------------------------------------------------


def test_get_recent_posts_zero_window(monitor):
    """hours_back=0 must return an empty list (cutoff == now)."""
    now = datetime.now(timezone.utc)
    post = TrumpPost(
        post_text="iran deal",
        timestamp=now,
        keywords_found=["iran deal"],
        sentiment="bearish",
        confidence=0.3,
    )
    _inject_posts(monitor, [post])

    # timestamp == cutoff — strictly less than cutoff required for inclusion.
    results = monitor.get_recent_posts(hours_back=0)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# T13: has_recent_catalyst returns newest qualifying post
# ---------------------------------------------------------------------------


def test_has_recent_catalyst_returns_newest(monitor):
    """has_recent_catalyst must return the most recent qualifying post."""
    now = datetime.now(timezone.utc)
    older = TrumpPost(
        post_text="old iran attack",
        timestamp=now - timedelta(minutes=20),
        keywords_found=["iran attack"],
        sentiment="bullish",
        confidence=0.3,
    )
    newer = TrumpPost(
        post_text="new military action",
        timestamp=now - timedelta(minutes=5),
        keywords_found=["military action"],
        sentiment="bullish",
        confidence=0.3,
    )
    _inject_posts(monitor, [older, newer])

    result = monitor.has_recent_catalyst(minutes_back=30)
    assert result is not None
    assert result.post_text == "new military action", (
        f"Expected newest post, got: {result.post_text}"
    )


def test_has_recent_catalyst_minimum_confidence_enforced(monitor):
    """Posts with confidence < 0.3 must not be returned as catalysts."""
    now = datetime.now(timezone.utc)
    low_conf = TrumpPost(
        post_text="iran",
        timestamp=now - timedelta(minutes=5),
        keywords_found=["iran deal"],
        sentiment="bearish",
        confidence=0.2,  # Below the 0.3 threshold.
    )
    _inject_posts(monitor, [low_conf])

    result = monitor.has_recent_catalyst(minutes_back=30)
    assert result is None, "Post with confidence=0.2 must not be a catalyst"


# ---------------------------------------------------------------------------
# T14: has_recent_catalyst returns None when no post is within the window
# ---------------------------------------------------------------------------


def test_has_recent_catalyst_no_recent_posts(monitor):
    """Empty history must return None."""
    assert monitor.has_recent_catalyst(minutes_back=30) is None


def test_has_recent_catalyst_post_outside_window(monitor):
    """A post older than minutes_back must not be returned."""
    now = datetime.now(timezone.utc)
    old = TrumpPost(
        post_text="iran attack yesterday",
        timestamp=now - timedelta(minutes=60),
        keywords_found=["iran attack"],
        sentiment="bullish",
        confidence=0.3,
    )
    _inject_posts(monitor, [old])

    result = monitor.has_recent_catalyst(minutes_back=30)
    assert result is None


# ---------------------------------------------------------------------------
# T15: Conflicting keyword counts resolve to the higher count
# ---------------------------------------------------------------------------


def test_sentiment_higher_count_wins(monitor):
    """When bullish-oil count > bearish-oil count, result is 'bullish'."""
    # Two bullish-oil matches vs one bearish-oil match.
    post = _make_post(
        "Iran attack imminent. Military action ordered. But iran talks failed."
    )
    result = monitor._analyze_post(post)

    assert result is not None
    assert result.sentiment == "bullish", (
        f"Bullish count should dominate; got '{result.sentiment}'"
    )


# ---------------------------------------------------------------------------
# T16: Tied bullish/bearish counts → fear keyword breaks the tie to 'bearish'
# ---------------------------------------------------------------------------


def test_sentiment_tie_broken_by_fear(monitor):
    """Equal bullish and bearish oil counts with a fear keyword → 'bearish'."""
    # One bullish-oil match, one bearish-oil match, one fear match.
    post = _make_post(
        "The iran attack is worrying but iran deal might prevent a recession."
    )
    result = monitor._analyze_post(post)

    assert result is not None
    # Tied: bullish_oil=1 (iran attack), bearish_oil=1 (iran deal), fear=1 (recession).
    assert result.sentiment == "bearish", (
        f"Fear keyword should break tie to 'bearish'; got '{result.sentiment}'"
    )


# ---------------------------------------------------------------------------
# T17: post_text is truncated to 500 characters
# ---------------------------------------------------------------------------


def test_post_text_truncated_to_500(monitor):
    """post_text in TrumpPost must never exceed 500 characters."""
    long_text = "iran attack " * 60  # ~720 chars.
    post = _make_post(long_text)
    result = monitor._analyze_post(post)

    assert result is not None
    assert len(result.post_text) <= 500, (
        f"post_text length {len(result.post_text)} exceeds 500"
    )


# ---------------------------------------------------------------------------
# T18: _parse_feed strips HTML tags
# ---------------------------------------------------------------------------


def test_parse_feed_strips_html_tags(monitor):
    """HTML markup inside <description> must be stripped from the text field."""
    rss_with_html = """<rss><channel>
    <item>
      <guid>id-html-1</guid>
      <description><![CDATA[<p>Iran <b>deal</b> reached. <a href="x">Read more</a></p>]]></description>
      <pubDate>Wed, 26 Mar 2026 12:00:00 +0000</pubDate>
    </item>
    </channel></rss>"""

    posts = monitor._parse_feed(rss_with_html)
    assert len(posts) == 1
    text = posts[0]["text"]
    assert "<" not in text, f"HTML tags remain in text: {text!r}"
    assert "Iran" in text and "deal" in text, f"Expected content present in: {text!r}"


# ---------------------------------------------------------------------------
# T19: _parse_feed handles CDATA wrappers
# ---------------------------------------------------------------------------


def test_parse_feed_cdata_wrapper(monitor):
    """CDATA wrappers must be stripped so the inner text is returned cleanly."""
    rss_cdata = """<rss><channel>
    <item>
      <guid>id-cdata-1</guid>
      <description><![CDATA[Sanctions iran starting now!]]></description>
      <pubDate>Wed, 26 Mar 2026 09:00:00 +0000</pubDate>
    </item>
    </channel></rss>"""

    posts = monitor._parse_feed(rss_cdata)
    assert len(posts) == 1
    assert posts[0]["text"] == "Sanctions iran starting now!", (
        f"Unexpected text: {posts[0]['text']!r}"
    )
