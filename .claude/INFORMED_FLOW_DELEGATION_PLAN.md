# Informed Flow Detection - Delegation Plan

## Overview
This plan uses Claude Code's agent delegation feature to spawn specialized agents for each task.
Run these commands in Claude Code terminal to execute.

---

## 🚀 DELEGATION COMMANDS

### Sprint 1: Core Detection (Days 1-4)

#### Task 1.1: Price Velocity Detector
```bash
/agent flow-detector Create the PriceVelocityDetector class in src/services/informed_flow/price_velocity_detector.py. 

Requirements:
1. Detect >0.5% price moves in 1-minute windows
2. Calculate z-score against 60-minute rolling baseline
3. Emit 'price_velocity_alert' via EventBus
4. Include unit tests with synthetic spike data
5. Use async/await pattern consistent with existing codebase

The detector should:
- Accept List[Candle] from risetrader-mcp:get_latest_candles
- NOT claim to detect institutional flows (MT4 tick volume ≠ exchange volume)
- Return Optional[InformedFlowAlert] with confidence score

Reference existing patterns in src/agents/data_ml/regime_detection_agent.py for event bus integration.
```

#### Task 1.2: Tick Clustering Detector
```bash
/agent flow-detector Create the TickClusteringDetector class in src/services/informed_flow/tick_clustering_detector.py.

Requirements:
1. Identify tick count bursts (>3x baseline)
2. Correlate tick bursts with price direction (same direction = confirmation)
3. Accept optional NewsFeedService to check for catalyst
4. Return ClusterAnalysis dataclass with:
   - is_anomaly: bool
   - tick_z_score: float
   - price_direction: str (up/down/flat)
   - has_news_catalyst: Optional[bool]
   - confidence: float (0-1)

Normal tick range: 1-50 ticks/minute
Anomaly threshold: 150+ ticks/minute

Include unit tests with synthetic data.
```

#### Task 1.3: Cross-Asset Monitor
```bash
/agent flow-detector Create the CrossAssetMonitor class in src/services/informed_flow/cross_asset_monitor.py.

Requirements:
1. Calculate rolling correlation between configured pairs:
   - CrudeOIL ↔ DXY
   - CrudeOIL ↔ VIX  
   - CrudeOIL ↔ XAUUSD
2. Alert when correlation exceeds 0.7 threshold
3. Store correlation history in database (create migration if needed)
4. Expose async method: calculate_rolling_correlation(symbol1, symbol2, window_minutes=10)

Use numpy for correlation calculation.
Integrate with ExogenousDataLoader for DXY/VIX data.
```

---

### Sprint 2: External Data (Days 5-8)

#### Task 2.1: Truth Social Monitor
```bash
/agent flow-detector Create the TruthSocialMonitor class in src/services/social/truth_social_monitor.py.

Requirements:
1. Poll Truth Social every 30 seconds
2. Detect new posts from @realDonaldTrump within 60 seconds
3. Extract market-moving keywords:
   - bullish_oil: ['iran attack', 'iran strike', 'bomb iran', 'military action']
   - bearish_oil: ['iran deal', 'iran talks', 'productive', 'peace']
   - market_fear: ['china', 'tariff', 'trade war', 'crash']
4. Emit 'trump_post_detected' event via EventBus with:
   - post_text: str
   - timestamp: datetime
   - keywords_found: List[str]
   - sentiment: str (bullish/bearish/neutral)
   - confidence: float

Use httpx for async requests.
Handle rate limiting gracefully.
Include mock test that doesn't hit actual API.
```

#### Task 2.2: News Feed Service
```bash
/agent flow-detector Create the NewsFeedService class in src/services/news/news_feed_service.py.

Requirements:
1. Integrate with free tier APIs:
   - NewsAPI.org (primary)
   - Finnhub (fallback)
2. Method: get_recent_news(symbols: List[str], lookback_minutes: int = 30) -> List[NewsItem]
3. Method: has_catalyst(symbol: str, timestamp: datetime) -> bool
4. NewsItem dataclass:
   - headline: str
   - source: str
   - published_at: datetime
   - relevance_score: float
   - url: str

Store API keys in environment variables.
Include integration test with mock responses.
```

---

### Sprint 3: Integration (Days 9-12)

#### Task 3.1: MCP Tools
```bash
/agent flow-detector Create MCP tools in src/mcp/tools/informed_flow_tools.py.

Add these tools following the pattern in src/mcp/tools/:

1. detect_informed_flow(symbol: str) -> InformedFlowStatus
   - Orchestrate all detectors
   - Return composite alert with confidence

2. get_trump_posts(hours_back: int = 24) -> List[TrumpPost]
   - Query TruthSocialMonitor history
   - Return recent posts with extracted sentiment

3. check_news_catalyst(symbol: str, minutes_back: int = 30) -> NewsAnalysis
   - Query NewsFeedService
   - Return whether news explains recent price movement

Register tools in mcp_server.py.
Add to risetrader-mcp tool list.
```

#### Task 3.2: Historical Analyzer CLI
```bash
/agent flow-detector Create CLI tool scripts/analyze_historical_flow.py.

Usage:
    python scripts/analyze_historical_flow.py \
        --symbol CrudeOIL \
        --start 2024-01-01 \
        --end 2024-12-31 \
        --output reports/flow_analysis.json

Requirements:
1. Scan our 13.5M candles for price velocity anomalies
2. Generate report of detected events with:
   - timestamp
   - price_change_pct
   - tick_burst (if any)
   - cross_asset_correlations at time
3. Calculate hypothetical strategy performance if traded
4. Export to JSON and markdown formats

Use asyncio for efficient database queries.
Include progress bar for long scans.
```

---

### Sprint 4: Testing & Dashboard (Days 13-14)

#### Task 4.1: Integration Tests
```bash
/agent mcp-verifier Create integration tests for informed flow detection in tests/integration/test_informed_flow.py.

Test scenarios:
1. Price velocity detection on synthetic spike
2. Tick clustering detection on synthetic burst
3. Cross-asset correlation calculation
4. Full detection pipeline end-to-end
5. MCP tool responses

Use real candle data from database (not mocks).
Mark tests that require external APIs as skip-able.
```

#### Task 4.2: Coordinate with Lead
```bash
/agent lead Review the informed flow detection implementation.

Verify:
1. All file ownership boundaries respected
2. No hardcoded fakes introduced
3. Integration tests pass
4. Event bus integration works
5. Documentation complete

Phase gate: Can we deploy this to paper trading?
```

---

## 📁 Files to Create

```
src/services/
├── informed_flow/
│   ├── __init__.py
│   ├── price_velocity_detector.py    # Sprint 1
│   ├── tick_clustering_detector.py   # Sprint 1
│   ├── cross_asset_monitor.py        # Sprint 1
│   └── schemas.py                    # Data classes
├── social/
│   ├── __init__.py
│   └── truth_social_monitor.py       # Sprint 2
└── news/
    ├── __init__.py
    └── news_feed_service.py          # Sprint 2

src/mcp/tools/
└── informed_flow_tools.py            # Sprint 3

scripts/
└── analyze_historical_flow.py        # Sprint 3

tests/integration/
└── test_informed_flow.py             # Sprint 4
```

---

## 🎯 Success Criteria

| Metric | Target |
|--------|--------|
| Detection Latency | < 5 seconds from event to alert |
| False Positive Rate | < 20% of HIGH alerts |
| Trump Post Detection | < 60 seconds from post |
| Historical Events Found | > 10 in 2024 CrudeOIL data |
| All Integration Tests | PASS |

---

## ⚡ Quick Start

To begin implementation immediately, run these commands in Claude Code:

```bash
# 1. Create directory structure
mkdir -p src/services/informed_flow src/services/social src/services/news

# 2. Start with core detection
/agent flow-detector Start Phase 1 Task 1.1 - Create PriceVelocityDetector

# 3. Monitor progress
/agent lead Check status of informed flow detection implementation
```

---

## 📊 Data Access

Agents can use these tools for data:
- `risetrader-mcp:get_latest_candles` - Real-time candle data
- `risetrader-mcp:compute_indicators` - Technical indicators
- `risetrader-db:query` - Direct database queries on 13.5M candles

Example query for historical analysis:
```sql
SELECT time, open, high, low, close, volume
FROM candles
WHERE symbol = 'CrudeOIL' 
  AND timeframe = 'M1'
  AND time BETWEEN '2024-01-01' AND '2024-12-31'
ORDER BY time
```
