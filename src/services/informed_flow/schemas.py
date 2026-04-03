"""
Shared data classes for the informed flow detection pipeline.

These schemas are the contract between all informed flow detectors
(price velocity, tick cluster, cross-asset, news, social) and the
composite InformedFlowDetector that aggregates their outputs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class InformedFlowAlert:
    """Alert emitted when anomalous price/tick activity is detected.

    Inputs:
        symbol: MT4 symbol string (e.g. 'CrudeOIL', 'GBPJPY').
        timestamp: UTC datetime of the detection event.
        alert_type: One of 'price_velocity', 'tick_cluster',
            'cross_asset', 'composite'.
        confidence: Normalised certainty score in [0.0, 1.0].
            Values >= 0.7 are considered high-confidence.
        price_change_pct: Percentage price move that triggered the
            alert (signed; negative = down).
        z_score: Standard-deviation distance from the rolling baseline.
            Values > 2.0 are anomalous.
        direction: 'up', 'down', or 'flat'.
        details: Arbitrary detector-specific metadata.
    """

    symbol: str
    timestamp: datetime
    alert_type: str  # 'price_velocity', 'tick_cluster', 'cross_asset', 'composite'
    confidence: float  # 0.0 to 1.0
    price_change_pct: float
    z_score: float
    direction: str  # 'up', 'down', 'flat'
    details: dict = field(default_factory=dict)


@dataclass
class ClusterAnalysis:
    """Result of tick clustering analysis for a single observation window.

    Inputs:
        is_anomaly: True when tick_z_score exceeds the configured threshold.
        tick_z_score: Z-score of tick count in the current window relative
            to the rolling baseline.
        price_direction: Net price direction over the window ('up', 'down',
            'flat').
        has_news_catalyst: True if a coincident news item was found, False
            if explicitly checked and none found, None if not checked.
        confidence: Combined confidence score in [0.0, 1.0].
        tick_count: Raw tick count in the analysis window.
        baseline_mean: Rolling mean tick count used as the baseline.
        baseline_std: Rolling std dev of tick count used for z-scoring.
            Callers must handle baseline_std == 0 before computing z-scores.
    """

    is_anomaly: bool
    tick_z_score: float
    price_direction: str  # 'up', 'down', 'flat'
    has_news_catalyst: Optional[bool] = None
    confidence: float = 0.0
    tick_count: int = 0
    baseline_mean: float = 0.0
    baseline_std: float = 0.0


@dataclass
class CorrelationAlert:
    """Alert when cross-asset rolling correlation exceeds threshold.

    Inputs:
        symbol1: Primary symbol (e.g. 'CrudeOIL').
        symbol2: Correlated symbol (e.g. 'BRENT_OIL').
        correlation: Pearson correlation coefficient in [-1.0, 1.0].
        window_minutes: Look-back window used to compute the correlation.
        timestamp: UTC datetime when the correlation was computed.
        threshold_exceeded: True when abs(correlation) >= the configured
            threshold (typically 0.7).
    """

    symbol1: str
    symbol2: str
    correlation: float
    window_minutes: int
    timestamp: datetime
    threshold_exceeded: bool = False


@dataclass
class NewsItem:
    """Single news article returned by a news provider.

    Inputs:
        headline: Full headline text.
        source: Publisher name (e.g. 'Reuters', 'Bloomberg').
        published_at: UTC publication datetime.
        relevance_score: Provider-assigned relevance score in [0.0, 1.0].
        url: Canonical article URL.
    """

    headline: str
    source: str
    published_at: datetime
    relevance_score: float
    url: str


@dataclass
class TrumpPost:
    """Detected social media post with potential market relevance.

    Inputs:
        post_text: Raw post content.
        timestamp: UTC datetime of the post.
        keywords_found: List of matched market-relevant keywords
            (e.g. ['oil', 'tariff', 'china']).
        sentiment: 'bullish', 'bearish', or 'neutral' — caller-derived.
        confidence: Confidence in the sentiment classification in [0.0, 1.0].
    """

    post_text: str
    timestamp: datetime
    keywords_found: List[str] = field(default_factory=list)
    sentiment: str = 'neutral'  # 'bullish', 'bearish', 'neutral'
    confidence: float = 0.0


@dataclass
class InformedFlowStatus:
    """Composite status aggregated from all active detectors.

    Inputs:
        symbol: MT4 symbol this status applies to.
        timestamp: UTC datetime of aggregation.
        overall_confidence: Weighted aggregate confidence across all
            firing detectors, in [0.0, 1.0].
        alerts: All InformedFlowAlert instances that contributed to
            this status.
        has_price_velocity: True if a price velocity detector fired.
        has_tick_cluster: True if a tick cluster detector fired.
        has_cross_asset_signal: True if a cross-asset correlation
            detector fired.
        has_news_catalyst: True if a news or social detector fired.
        recommendation: Suggested action — 'BUY', 'SELL', or 'HOLD'.
            Callers must apply their own risk rules; this is a hint only.
    """

    symbol: str
    timestamp: datetime
    overall_confidence: float
    alerts: List[InformedFlowAlert] = field(default_factory=list)
    has_price_velocity: bool = False
    has_tick_cluster: bool = False
    has_cross_asset_signal: bool = False
    has_news_catalyst: bool = False
    recommendation: str = 'HOLD'  # 'BUY', 'SELL', 'HOLD'
