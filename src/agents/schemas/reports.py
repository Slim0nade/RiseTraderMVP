"""
Analyst report and debate schemas for Analysis and Debate layer agents.
Used by Technical Analyst, Fundamental Analyst, Sentiment Analyst, and Devil's Advocate.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class TrendDirection(str, Enum):
    """Trend direction classification."""

    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


class MarketRegime(str, Enum):
    """Market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    BREAKOUT = "breakout"
    REVERSAL = "reversal"


class SentimentPolarity(str, Enum):
    """Sentiment polarity classification."""

    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class TechnicalReport(BaseModel):
    """
    Technical analysis report from Technical Analyst Agent.

    Provides comprehensive technical analysis including trends,
    support/resistance, indicators, and chart patterns.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "timeframe": "H4",
                "trend_direction": "bullish",
                "confidence": 0.72,
                "key_levels": {"support": [2640, 2630], "resistance": [2670, 2685]},
                "indicators": {"rsi": 58.5, "macd": 2.3, "ema_20": 2648.0},
                "summary": "Bullish trend with RSI divergence and support holding"
            }
        }
    )

    # Report identification
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    timeframe: str = Field(
        ...,
        description="Chart timeframe analyzed"
    )

    # Trend analysis
    trend_direction: TrendDirection = Field(
        ...,
        description="Overall trend direction"
    )

    trend_strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Trend strength score (0.0-1.0)"
    )

    market_regime: Optional[MarketRegime] = Field(
        None,
        description="Current market regime"
    )

    # Confidence
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall analysis confidence (0.0-1.0)"
    )

    # Key price levels
    key_levels: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Key support and resistance levels"
    )

    current_price: Optional[float] = Field(
        None,
        gt=0,
        description="Current market price"
    )

    # Technical indicators
    indicators: Dict[str, float] = Field(
        default_factory=dict,
        description="Technical indicator values (RSI, MACD, EMAs, etc.)"
    )

    # Chart patterns
    patterns_detected: List[str] = Field(
        default_factory=list,
        description="List of detected chart patterns"
    )

    # Signals
    bullish_signals: List[str] = Field(
        default_factory=list,
        description="List of bullish signals identified"
    )

    bearish_signals: List[str] = Field(
        default_factory=list,
        description="List of bearish signals identified"
    )

    # Summary
    summary: str = Field(
        ...,
        min_length=20,
        description="Concise technical analysis summary"
    )

    detailed_reasoning: Optional[str] = Field(
        None,
        description="Detailed reasoning and analysis"
    )

    # Metadata
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when analysis was performed"
    )

    data_points_analyzed: Optional[int] = Field(
        None,
        ge=0,
        description="Number of candlesticks/data points analyzed"
    )


class FundamentalReport(BaseModel):
    """
    Fundamental analysis report from Fundamental Analyst Agent.

    Analyzes macroeconomic factors, economic calendar events,
    and fundamental drivers affecting the instrument.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "fundamental_bias": "bullish",
                "confidence": 0.65,
                "key_factors": ["fed_dovish", "inflation_rising", "usd_weakening"],
                "summary": "Bullish fundamentals: Fed dovish, inflation up, USD weak"
            }
        }
    )

    # Report identification
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    # Fundamental bias
    fundamental_bias: TrendDirection = Field(
        ...,
        description="Overall fundamental bias"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Analysis confidence (0.0-1.0)"
    )

    # Key factors
    key_factors: List[str] = Field(
        default_factory=list,
        description="Key fundamental factors identified"
    )

    bullish_factors: List[str] = Field(
        default_factory=list,
        description="Bullish fundamental factors"
    )

    bearish_factors: List[str] = Field(
        default_factory=list,
        description="Bearish fundamental factors"
    )

    # Economic events
    upcoming_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Upcoming economic calendar events"
    )

    recent_events_impact: Optional[str] = Field(
        None,
        description="Impact of recent economic events"
    )

    # Macro analysis
    macro_outlook: Optional[str] = Field(
        None,
        description="Macroeconomic outlook"
    )

    correlation_analysis: Optional[Dict[str, float]] = Field(
        None,
        description="Correlation with other instruments (e.g., {'DXY': -0.75})"
    )

    # Summary
    summary: str = Field(
        ...,
        min_length=20,
        description="Concise fundamental analysis summary"
    )

    detailed_reasoning: Optional[str] = Field(
        None,
        description="Detailed reasoning and analysis"
    )

    # Metadata
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when analysis was performed"
    )

    data_sources: List[str] = Field(
        default_factory=list,
        description="Data sources used (e.g., ['fred', 'economic_calendar'])"
    )


class SentimentReport(BaseModel):
    """
    Sentiment analysis report from Sentiment Analyst Agent.

    Analyzes market sentiment from news, social media, and positioning data.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "sentiment_polarity": "positive",
                "sentiment_score": 0.68,
                "confidence": 0.70,
                "news_sentiment": 0.72,
                "summary": "Positive sentiment: bullish news flow and retail positioning"
            }
        }
    )

    # Report identification
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    # Sentiment metrics
    sentiment_polarity: SentimentPolarity = Field(
        ...,
        description="Overall sentiment polarity"
    )

    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Sentiment score (-1.0=very negative, 0=neutral, 1.0=very positive)"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Analysis confidence (0.0-1.0)"
    )

    # Sentiment sources
    news_sentiment: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="News sentiment score"
    )

    social_media_sentiment: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Social media sentiment score"
    )

    positioning_sentiment: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Market positioning sentiment (COT, retail positioning)"
    )

    # Sentiment indicators
    fear_greed_index: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Fear & Greed index (0=extreme fear, 100=extreme greed)"
    )

    sentiment_momentum: Optional[str] = Field(
        None,
        description="Sentiment momentum: improving, stable, deteriorating"
    )

    # Key themes
    positive_themes: List[str] = Field(
        default_factory=list,
        description="Positive sentiment themes"
    )

    negative_themes: List[str] = Field(
        default_factory=list,
        description="Negative sentiment themes"
    )

    # Summary
    summary: str = Field(
        ...,
        min_length=20,
        description="Concise sentiment analysis summary"
    )

    detailed_reasoning: Optional[str] = Field(
        None,
        description="Detailed reasoning and analysis"
    )

    # Metadata
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when analysis was performed"
    )

    data_sources: List[str] = Field(
        default_factory=list,
        description="Data sources used"
    )

    articles_analyzed: Optional[int] = Field(
        None,
        ge=0,
        description="Number of articles analyzed"
    )


class DebateOutcome(BaseModel):
    """
    Debate outcome from Devil's Advocate Agent.

    Synthesizes analyst reports and challenges the consensus
    to produce a balanced trading decision.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "Gold",
                "consensus_direction": "bullish",
                "consensus_strength": 0.70,
                "debate_summary": "Strong bullish consensus with minor technical concerns",
                "proceed_with_trade": True,
                "recommended_caution_level": "moderate"
            }
        }
    )

    # Debate identification
    symbol: str = Field(
        ...,
        description="Trading symbol"
    )

    debate_id: UUID = Field(
        ...,
        description="Unique debate session identifier"
    )

    # Analyst inputs
    technical_report_id: Optional[UUID] = Field(
        None,
        description="ID of technical analysis report"
    )

    fundamental_report_id: Optional[UUID] = Field(
        None,
        description="ID of fundamental analysis report"
    )

    sentiment_report_id: Optional[UUID] = Field(
        None,
        description="ID of sentiment analysis report"
    )

    # Consensus analysis
    consensus_direction: TrendDirection = Field(
        ...,
        description="Consensus trade direction from all analysts"
    )

    consensus_strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of analyst consensus (0.0-1.0)"
    )

    analyst_agreement: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Agreement level between analysts (1.0=full agreement)"
    )

    # Devil's advocate challenges
    counter_arguments: List[str] = Field(
        default_factory=list,
        description="Counter-arguments and concerns raised"
    )

    risk_factors: List[str] = Field(
        default_factory=list,
        description="Identified risk factors"
    )

    conflicting_signals: List[str] = Field(
        default_factory=list,
        description="Conflicting signals between analysts"
    )

    # Decision
    proceed_with_trade: bool = Field(
        ...,
        description="Whether to proceed with trade after debate"
    )

    recommended_caution_level: str = Field(
        ...,
        description="Caution level: low, moderate, high"
    )

    confidence_adjustment: Optional[float] = Field(
        None,
        description="Confidence adjustment after debate (-1.0 to 1.0)"
    )

    # Summary
    debate_summary: str = Field(
        ...,
        min_length=20,
        description="Concise debate outcome summary"
    )

    detailed_reasoning: Optional[str] = Field(
        None,
        description="Detailed debate reasoning"
    )

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list,
        description="Specific recommendations for trade execution"
    )

    # Metadata
    debated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when debate concluded"
    )

    debate_duration_ms: Optional[int] = Field(
        None,
        ge=0,
        description="Debate duration in milliseconds"
    )
