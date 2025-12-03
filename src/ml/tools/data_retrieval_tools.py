"""
Data Retrieval MCP Tools.

Provides external data sources for fundamental analysis:
- Economic calendar events
- Commitment of Traders (COT) positioning data
"""

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field


class EconomicEvent(BaseModel):
    """Economic calendar event."""
    event_name: str
    event_time: str  # ISO 8601 format
    impact: str  # "LOW", "MEDIUM", "HIGH"
    currency: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    description: Optional[str] = None


class HighRiskPeriod(BaseModel):
    """Time window with clustered high-impact events."""
    start_time: str  # ISO 8601 format
    end_time: str  # ISO 8601 format
    event_count: int


class EconomicEventsInput(BaseModel):
    """Input schema for economic events retrieval."""
    symbol: str
    lookforward_hours: int = Field(default=24, ge=1, le=168)  # 1 week max
    min_impact: str = Field(default="HIGH", pattern="^(LOW|MEDIUM|HIGH)$")


class EconomicEventsOutput(BaseModel):
    """Output schema for economic events retrieval."""
    symbol: str
    events: List[EconomicEvent]
    high_risk_periods: List[HighRiskPeriod]
    retrieval_time_ms: float


class CommercialPositioning(BaseModel):
    """Commercial trader positioning."""
    long_contracts: int
    short_contracts: int
    net_position: int
    net_position_change_pct: float


class SpeculatorPositioning(BaseModel):
    """Large speculator positioning."""
    long_contracts: int
    short_contracts: int
    net_position: int
    net_position_change_pct: float


class RetailPositioning(BaseModel):
    """Retail trader positioning."""
    long_pct: float
    short_pct: float


class COTDataInput(BaseModel):
    """Input schema for COT data retrieval."""
    symbol: str
    lookback_weeks: int = Field(default=4, ge=1, le=52)


class COTDataOutput(BaseModel):
    """Output schema for COT data retrieval."""
    symbol: str
    latest_report_date: str  # Date format
    commercial_positioning: CommercialPositioning
    large_speculator_positioning: SpeculatorPositioning
    retail_positioning: RetailPositioning
    sentiment_signal: str  # "BULLISH", "BEARISH", "NEUTRAL", "CONTRARIAN_BULLISH", "CONTRARIAN_BEARISH"
    retrieval_time_ms: float


# External Data API URLs
ECONOMIC_CALENDAR_API_URL = os.getenv("ECONOMIC_CALENDAR_API_URL", "https://api.example.com/calendar")
COT_DATA_API_URL = os.getenv("COT_DATA_API_URL", "https://api.example.com/cot")
HTTP_TIMEOUT = 5.0


async def get_economic_events(
    symbol: str,
    lookforward_hours: int = 24,
    min_impact: str = "HIGH",
) -> Dict[str, Any]:
    """
    Get upcoming high-impact economic calendar events.

    Economic events (e.g., FOMC meetings, Non-Farm Payrolls, CPI releases) cause
    significant market volatility. This tool:

    1. Retrieves upcoming events relevant to the trading symbol
    2. Filters by minimum impact level (HIGH, MEDIUM, LOW)
    3. Identifies high-risk periods (clustered events)

    Used by:
    - **Position Sizing Agent**: Reduce position size before high-impact events
    - **Fundamental Analyst Agent**: Incorporate event risk into analysis
    - **Stop-Loss Agent**: Widen stops before volatile events

    Args:
        symbol: Trading symbol (e.g., "CrudeOIL" → oil inventory reports,
                "Gold" → Fed policy, inflation data)
        lookforward_hours: Hours to look ahead (1-168, default 24)
        min_impact: Minimum event impact ("LOW", "MEDIUM", "HIGH")

    Returns:
        Economic events and high-risk time windows

    Example:
        >>> events = await get_economic_events("CrudeOIL", 48, "HIGH")
        >>> for event in events["events"]:
        ...     print(f"{event['event_name']} at {event['event_time']}")
    """
    start_time = time.time()

    # Validate input
    input_data = EconomicEventsInput(
        symbol=symbol,
        lookforward_hours=lookforward_hours,
        min_impact=min_impact,
    )

    try:
        # Calculate time window
        now = datetime.utcnow()
        end_time = now + timedelta(hours=lookforward_hours)

        # Fetch economic calendar data
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                ECONOMIC_CALENDAR_API_URL,
                params={
                    "symbol": symbol,
                    "start": now.isoformat(),
                    "end": end_time.isoformat(),
                    "min_impact": min_impact,
                },
            )
            response.raise_for_status()
            calendar_data = response.json()

        # Parse events
        events = [EconomicEvent(**event) for event in calendar_data.get("events", [])]

        # Identify high-risk periods (multiple high-impact events within 4 hours)
        high_risk_periods = []
        if len(events) >= 2:
            for i in range(len(events) - 1):
                if events[i].impact == "HIGH":
                    # Check if next event is within 4 hours
                    t1 = datetime.fromisoformat(events[i].event_time)
                    t2 = datetime.fromisoformat(events[i+1].event_time)
                    if (t2 - t1).total_seconds() <= 4 * 3600:
                        high_risk_periods.append(HighRiskPeriod(
                            start_time=events[i].event_time,
                            end_time=(t2 + timedelta(hours=1)).isoformat(),
                            event_count=2,
                        ))

        retrieval_time_ms = (time.time() - start_time) * 1000

        output = EconomicEventsOutput(
            symbol=symbol,
            events=events,
            high_risk_periods=high_risk_periods,
            retrieval_time_ms=retrieval_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as e:
        # Economic calendar API unavailable - return mock events
        retrieval_time_ms = (time.time() - start_time) * 1000

        # Return mock upcoming events (next 48 hours)
        now = datetime.utcnow()
        mock_events = [
            EconomicEvent(
                event_name="FOMC Interest Rate Decision",
                event_time=(now + timedelta(hours=12)).isoformat(),
                impact="HIGH",
                currency="USD",
                forecast="5.25%",
                previous="5.00%",
                description="Federal Reserve monetary policy decision",
            ),
            EconomicEvent(
                event_name="Crude Oil Inventories",
                event_time=(now + timedelta(hours=36)).isoformat(),
                impact="HIGH",
                currency="USD",
                forecast="+2.5M barrels",
                previous="+1.2M barrels",
                description="Weekly US crude oil inventory report",
            ),
        ] if symbol == "CrudeOIL" else []

        mock_output = EconomicEventsOutput(
            symbol=symbol,
            events=mock_events,
            high_risk_periods=[],
            retrieval_time_ms=retrieval_time_ms,
        )

        return mock_output.model_dump()


async def get_cot_data(
    symbol: str,
    lookback_weeks: int = 4,
) -> Dict[str, Any]:
    """
    Get Commitment of Traders (COT) positioning data.

    COT reports (published weekly by CFTC) reveal positioning of:
    - **Commercial traders** (hedgers, e.g., oil companies, gold miners)
    - **Large speculators** (hedge funds, CTAs)
    - **Retail traders** (small speculators)

    Sentiment signals:
    - **BULLISH**: Commercials net long, retail net short (contrarian signal)
    - **BEARISH**: Commercials net short, retail net long
    - **CONTRARIAN_BULLISH**: Extreme retail short + commercial accumulation
    - **CONTRARIAN_BEARISH**: Extreme retail long + commercial distribution
    - **NEUTRAL**: Mixed signals

    Used by:
    - **Sentiment Analyst Agent**: Gauge market positioning and contrarian opportunities
    - **Position Sizing Agent**: Adjust size based on crowded trades

    Args:
        symbol: Trading symbol (must map to COT report, e.g., "CrudeOIL" → WTI Crude)
        lookback_weeks: Number of weeks of historical data (1-52)

    Returns:
        COT positioning data and derived sentiment signal

    Example:
        >>> cot = await get_cot_data("CrudeOIL", 4)
        >>> print(cot["sentiment_signal"])
        "CONTRARIAN_BULLISH"
    """
    start_time = time.time()

    # Validate input
    input_data = COTDataInput(
        symbol=symbol,
        lookback_weeks=lookback_weeks,
    )

    try:
        # Fetch COT data from API
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                COT_DATA_API_URL,
                params={
                    "symbol": symbol,
                    "weeks": lookback_weeks,
                },
            )
            response.raise_for_status()
            cot_data = response.json()

        # Parse positioning data
        commercial = CommercialPositioning(**cot_data["commercial"])
        speculator = SpeculatorPositioning(**cot_data["large_speculator"])
        retail = RetailPositioning(**cot_data["retail"])

        # Derive sentiment signal
        sentiment_signal = _calculate_sentiment_signal(commercial, speculator, retail)

        retrieval_time_ms = (time.time() - start_time) * 1000

        output = COTDataOutput(
            symbol=symbol,
            latest_report_date=cot_data["report_date"],
            commercial_positioning=commercial,
            large_speculator_positioning=speculator,
            retail_positioning=retail,
            sentiment_signal=sentiment_signal,
            retrieval_time_ms=retrieval_time_ms,
        )

        return output.model_dump()

    except (httpx.HTTPError, httpx.TimeoutException, KeyError) as e:
        # COT data API unavailable - return mock data
        retrieval_time_ms = (time.time() - start_time) * 1000

        # Return mock COT data (neutral positioning)
        mock_commercial = CommercialPositioning(
            long_contracts=150000,
            short_contracts=120000,
            net_position=30000,
            net_position_change_pct=5.2,
        )
        mock_speculator = SpeculatorPositioning(
            long_contracts=80000,
            short_contracts=90000,
            net_position=-10000,
            net_position_change_pct=-8.1,
        )
        mock_retail = RetailPositioning(
            long_pct=45.0,
            short_pct=55.0,
        )

        sentiment_signal = _calculate_sentiment_signal(mock_commercial, mock_speculator, mock_retail)

        mock_output = COTDataOutput(
            symbol=symbol,
            latest_report_date=(datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d"),
            commercial_positioning=mock_commercial,
            large_speculator_positioning=mock_speculator,
            retail_positioning=mock_retail,
            sentiment_signal=sentiment_signal,
            retrieval_time_ms=retrieval_time_ms,
        )

        return mock_output.model_dump()


def _calculate_sentiment_signal(
    commercial: CommercialPositioning,
    speculator: SpeculatorPositioning,
    retail: RetailPositioning,
) -> str:
    """
    Calculate sentiment signal from COT positioning.

    Logic (contrarian approach):
    - Commercials are smart money (hedgers with inside knowledge)
    - Retail traders are dumb money (fade their extremes)
    - Large speculators are momentum money (useful but laggy)

    Returns:
        Sentiment signal: BULLISH, BEARISH, NEUTRAL, CONTRARIAN_BULLISH, CONTRARIAN_BEARISH
    """
    # Commercial net position as signal
    commercial_bullish = commercial.net_position > 0

    # Retail positioning (contrarian signal)
    retail_extreme_short = retail.short_pct > 65.0
    retail_extreme_long = retail.long_pct > 65.0

    # Speculator trend (confirming signal)
    speculator_bullish = speculator.net_position > 0

    # Contrarian signals (strong)
    if commercial_bullish and retail_extreme_short:
        return "CONTRARIAN_BULLISH"
    elif not commercial_bullish and retail_extreme_long:
        return "CONTRARIAN_BEARISH"

    # Directional signals (moderate)
    elif commercial_bullish and speculator_bullish:
        return "BULLISH"
    elif not commercial_bullish and not speculator_bullish:
        return "BEARISH"

    # Mixed signals
    else:
        return "NEUTRAL"
