# Feature Specification: Dashboard API Service

**Feature Branch**: `002-fastapi-dashboard-api`
**Created**: 2025-11-24
**Status**: Draft
**Input**: User description: "Build a complete FastAPI service to serve market data from PostgreSQL database, and various price forecasts as well as accounts balance and portfolios strategy allocations to React dashboard with real-time MT4 integration"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Real-Time Market Data (Priority: P1)

As a trader, I need to view live market prices and historical price data in the dashboard so that I can make informed trading decisions based on current market conditions.

**Why this priority**: Real-time market data is the foundation of the trading system. Without it, traders cannot see current prices, make decisions, or monitor market movements. This is the most critical functionality that must work before any other features.

**Independent Test**: Can be fully tested by opening the dashboard, selecting a symbol (e.g., CrudeOIL), and verifying that current price and historical chart data appears. Delivers immediate value by showing traders what's happening in the market right now.

**Acceptance Scenarios**:

1. **Given** the dashboard is loaded, **When** I navigate to the Market Data page, **Then** I see a list of available trading symbols
2. **Given** I select a symbol (e.g., CrudeOIL), **When** the data loads, **Then** I see the current price, OHLC values (Open, High, Low, Close), and volume
3. **Given** I select a timeframe (M1, M5, M15, H1, etc.), **When** the chart refreshes, **Then** I see historical price data for that timeframe with up to 500 candlesticks
4. **Given** market data is streaming from MT4, **When** new prices arrive, **Then** the dashboard updates automatically without requiring a page refresh
5. **Given** the database contains no data for a symbol, **When** I select that symbol, **Then** I see a clear message indicating no data is available

---

### User Story 2 - Monitor Account Balance and Trading Activity (Priority: P2)

As a trader, I need to view my current account balance, open positions, and recent trading history so that I can track my portfolio performance and manage risk.

**Why this priority**: After seeing market data, traders need to know their current financial position. This enables risk management and informed decision-making about new trades. It's the second most important feature for active trading.

**Independent Test**: Can be tested by connecting to a demo MT4 account, executing a trade, and verifying the dashboard shows the updated balance, open positions, and trade history. Delivers value by giving traders visibility into their portfolio.

**Acceptance Scenarios**:

1. **Given** I'm logged into the dashboard, **When** I navigate to the Trading page, **Then** I see my current account balance
2. **Given** I have open positions, **When** the Trading page loads, **Then** I see a list of all open positions with entry price, current price, unrealized P&L, and position size
3. **Given** I have executed trades today, **When** I view trade history, **Then** I see all completed trades with entry/exit prices, profit/loss, and timestamps
4. **Given** account balance changes (e.g., from a closed trade), **When** the update occurs, **Then** the displayed balance updates in real-time
5. **Given** multiple trading symbols are active, **When** viewing positions, **Then** I can filter positions by symbol

---

### User Story 3 - View Price Forecasts and Strategy Allocations (Priority: P3)

As a trader, I need to see AI-generated price forecasts and current strategy allocations so that I can understand the system's predictions and how capital is distributed across different trading strategies.

**Why this priority**: Forecasts and strategy allocations provide advanced insights for optimization and decision-making. While valuable, the system can function for basic trading without these features. They enhance decision quality but aren't required for core trading operations.

**Independent Test**: Can be tested by viewing the Forecasts page and verifying predicted price movements are displayed, and checking the Strategies page to see how capital is allocated. Delivers value by showing traders what the AI predicts and how the system is positioned.

**Acceptance Scenarios**:

1. **Given** price forecasts have been generated, **When** I navigate to the Forecasts page, **Then** I see predicted price movements for the next 1 hour, 4 hours, and 24 hours
2. **Given** I select a forecast, **When** I view details, **Then** I see confidence levels, prediction timestamps, and actual vs predicted comparison (if available)
3. **Given** multiple trading strategies are active, **When** I view the Strategies page, **Then** I see each strategy's name, allocated capital, current status (active/paused), and performance metrics
4. **Given** a strategy's allocation changes, **When** the update occurs, **Then** the dashboard reflects the new allocation percentages
5. **Given** forecasts are updated hourly, **When** new forecasts arrive, **Then** the dashboard displays the latest predictions without manual refresh

---

### Edge Cases

- What happens when the database connection is lost while fetching market data?
  - System should display a user-friendly error message and attempt to reconnect automatically
  - Cached data should remain visible until connection is restored

- How does the system handle when MT4 is disconnected?
  - Dashboard should show a "Disconnected" status indicator
  - Historical data should still be accessible from the database
  - System should attempt to reconnect and update status when MT4 comes back online

- What happens when a user requests data for a time range that doesn't exist in the database?
  - System should return an empty dataset with a clear message
  - Chart should show "No data available for selected time range"

- How does the system handle extremely high-frequency data updates (e.g., tick-level data)?
  - System should throttle UI updates to a reasonable refresh rate (e.g., once per second maximum)
  - Prevent browser performance degradation from excessive DOM updates

- What happens when multiple users are viewing the same dashboard simultaneously?
  - Each user should receive real-time updates independently
  - System should handle concurrent database queries efficiently without locking

## Requirements *(mandatory)*

### Functional Requirements

**Market Data Service**:

- **FR-001**: System MUST provide an endpoint to retrieve current market prices for any available trading symbol
- **FR-002**: System MUST provide an endpoint to retrieve historical OHLCV data (Open, High, Low, Close, Volume) with configurable timeframes (M1, M5, M15, M30, H1, H4, D1, W1, MN1)
- **FR-003**: System MUST allow filtering historical data by symbol, timeframe, and date range
- **FR-004**: System MUST support pagination for large datasets to prevent timeouts and memory issues
- **FR-005**: System MUST return data in a format compatible with charting libraries (timestamp, OHLC values)
- **FR-006**: System MUST provide real-time market data updates through WebSocket or Server-Sent Events connections
- **FR-007**: System MUST validate all client requests and return appropriate error codes (400 for invalid requests, 404 for not found, 500 for server errors)

**Account & Trading Service**:

- **FR-008**: System MUST provide an endpoint to retrieve current account balance from the connected MT4 account
- **FR-009**: System MUST provide an endpoint to retrieve all open positions with details including symbol, entry price, current price, unrealized P&L, position size, and timestamps
- **FR-010**: System MUST provide an endpoint to retrieve trading history with filters for date range, symbol, and trade type (buy/sell)
- **FR-011**: System MUST calculate and display profit/loss for closed trades and unrealized P&L for open positions
- **FR-012**: System MUST update account balance and positions in real-time when changes occur in MT4

**Forecasting Service**:

- **FR-013**: System MUST provide an endpoint to retrieve the latest price forecasts for available symbols
- **FR-014**: System MUST return forecast data including predicted price, confidence level, forecast horizon (1h, 4h, 24h), and generation timestamp
- **FR-015**: System MUST allow comparison between forecast predictions and actual outcomes for accuracy tracking
- **FR-016**: System MUST maintain a history of forecasts for backtesting and analysis purposes

**Strategy & Portfolio Service**:

- **FR-017**: System MUST provide an endpoint to retrieve all active trading strategies with their current status
- **FR-018**: System MUST return strategy allocation data showing percentage of capital assigned to each strategy
- **FR-019**: System MUST provide strategy performance metrics including total return, win rate, Sharpe ratio, and drawdown
- **FR-020**: System MUST allow viewing strategy allocation changes over time

**System Integration**:

- **FR-021**: System MUST authenticate all API requests to prevent unauthorized access
- **FR-022**: System MUST implement CORS (Cross-Origin Resource Sharing) to allow dashboard access from configured domains
- **FR-023**: System MUST maintain persistent database connections to PostgreSQL for data retrieval
- **FR-024**: System MUST integrate with the existing MT4 integration service to receive real-time updates
- **FR-025**: System MUST log all API requests and errors for monitoring and debugging
- **FR-026**: System MUST provide a health check endpoint to verify service availability
- **FR-027**: System MUST handle graceful shutdown to close all active connections properly

**Data Consistency**:

- **FR-028**: System MUST ensure data returned to the dashboard matches data stored in the database
- **FR-029**: System MUST handle concurrent read requests without data corruption
- **FR-030**: System MUST cache frequently accessed data to reduce database load and improve response times

### Key Entities *(include if feature involves data)*

- **MarketData**: Represents OHLCV price data for a trading symbol at a specific timeframe and timestamp. Includes open, high, low, close prices, volume, change metrics, and source (MT4 or imported). Related to Indicators.

- **Indicators**: Represents technical indicator values (RSI, MACD, Bollinger Bands, Moving Averages, ATR, etc.) calculated for a specific market data point. Linked to MarketData via foreign key relationship.

- **Account**: Represents the MT4 trading account with current balance, equity, margin, free margin, and account number. Updated in real-time from MT4.

- **Position**: Represents an open trading position with symbol, entry price, current price, position size, direction (buy/sell), unrealized profit/loss, and opening timestamp.

- **Trade**: Represents a completed trading transaction with entry price, exit price, realized profit/loss, position size, symbol, entry/exit timestamps, and trade type.

- **Forecast**: Represents an AI-generated price prediction with predicted price, confidence level, forecast horizon (1h/4h/24h), generation timestamp, model used, and actual outcome (if available).

- **Strategy**: Represents a trading strategy configuration with name, status (active/paused), allocated capital, risk parameters, and performance metrics.

- **StrategyAllocation**: Represents the distribution of capital across different strategies with strategy name, allocated percentage, allocated amount, and last update timestamp.

- **StrategyPerformance**: Represents performance metrics for a strategy including total return, win rate, Sharpe ratio, max drawdown, number of trades, and time period.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Traders can view current market prices for any symbol within 1 second of page load
- **SC-002**: System can serve historical chart data (500 candlesticks) in under 2 seconds for any timeframe
- **SC-003**: Dashboard displays account balance updates within 3 seconds of a trade being executed in MT4
- **SC-004**: System handles at least 50 concurrent users viewing different symbols without performance degradation
- **SC-005**: 95% of API requests complete successfully without errors under normal operating conditions
- **SC-006**: Real-time price updates appear on the dashboard within 5 seconds of the price change occurring in MT4
- **SC-007**: Users can access 30 days of historical data for any symbol and timeframe without timeout errors
- **SC-008**: System maintains 99.5% uptime during market hours (measured over 1 month)
- **SC-009**: Forecast accuracy is measured and displayed, with at least 60% of forecasts directionally correct (predicted direction matches actual price movement)
- **SC-010**: Traders can view complete trading history for the past 90 days without pagination delays exceeding 3 seconds per page

## Assumptions *(mandatory)*

1. **Database Access**: PostgreSQL database is already populated with market data from MT4 integration service. The database schema includes tables for market_data, indicators, positions, trades, forecasts, and strategies.

2. **MT4 Integration**: The MT4 integration service (from feature 001) is operational and actively streaming market data, account updates, and position changes via Redis pub/sub or ZeroMQ.

3. **Authentication**: Initial version will support API key-based authentication. More advanced authentication (JWT, OAuth2) will be added in future phases.

4. **Real-time Technology**: WebSocket or Server-Sent Events (SSE) will be used for real-time dashboard updates. The choice depends on browser compatibility requirements and deployment infrastructure.

5. **Data Retention**: Historical market data is retained for at least 90 days. Older data may be archived but should remain accessible for backtesting purposes.

6. **Performance Baselines**: Success criteria assume standard deployment on cloud infrastructure (e.g., AWS t3.medium instance or equivalent) with at least 4GB RAM and SSD storage.

7. **Dashboard Framework**: The React dashboard (separate component) is already built and expects specific API response formats. API responses will conform to the existing dashboard expectations for seamless integration.

8. **Timeframe Standards**: All timeframes use MT4 standard notation (M1, M5, M15, M30, H1, H4, D1, W1, MN1) matching the database ENUM values.

9. **Error Handling**: All API endpoints will return standard HTTP status codes and JSON error responses with user-friendly messages suitable for display in the dashboard.

10. **Deployment Model**: The service will run in a Docker container as defined in docker-compose.yml, with dependencies on PostgreSQL and Redis containers.

## Scope *(mandatory)*

### In Scope

- REST API endpoints for retrieving market data, account information, trading history, forecasts, and strategy allocations
- Real-time data streaming to dashboard via WebSocket or Server-Sent Events
- CORS configuration to allow dashboard access
- Health check and monitoring endpoints
- API request authentication and validation
- Error handling and logging
- Database connection pooling and query optimization
- Integration with existing MT4 service for real-time updates
- Docker container deployment configuration

### Out of Scope

- Dashboard UI development (assumes dashboard already exists)
- Trading execution capabilities (placing/closing trades via API)
- User management and multi-user authentication
- ML model training or forecast generation (assumes forecasts are already generated)
- Strategy configuration or modification via API
- Historical data import/export functionality
- Advanced analytics or reporting features
- Mobile app support
- Email/SMS notifications
- Third-party integrations (beyond MT4)
- Payment processing or subscription management

## Dependencies *(mandatory)*

### External Dependencies

1. **PostgreSQL Database**: Service requires active PostgreSQL instance with populated market_data, indicators, positions, trades, forecasts, and strategies tables
2. **Redis**: Required for pub/sub messaging to receive real-time updates from MT4 integration service
3. **MT4 Integration Service**: Depends on the MT4 integration service (feature 001) being operational and streaming data
4. **React Dashboard**: Assumes dashboard application exists and is configured to consume the API

### Internal Dependencies

1. **Database Models**: Requires SQLAlchemy ORM models for all entities (MarketData, Indicators, Position, Trade, Forecast, Strategy, etc.)
2. **Repository Layer**: Depends on database repository implementations for data access
3. **Environment Configuration**: Requires environment variables for database connection, Redis connection, CORS origins, and API keys

### Technical Dependencies

1. Must run in Docker container environment
2. Requires network access between API container, PostgreSQL container, and Redis container
3. Requires port mapping (8003 → 8000) for external access from dashboard
4. Must support HTTP/2 for Server-Sent Events (if SSE chosen for real-time updates)

## Future Enhancements *(optional)*

1. **GraphQL API**: Provide GraphQL endpoint alongside REST API for more flexible data queries
2. **WebSocket Compression**: Implement compression for real-time data streams to reduce bandwidth
3. **Advanced Caching**: Implement Redis caching layer for frequently accessed data (e.g., latest prices)
4. **Rate Limiting**: Add per-client rate limiting to prevent abuse
5. **API Versioning**: Implement versioned API endpoints (/api/v1, /api/v2) for backward compatibility
6. **Trading Execution**: Add endpoints to place, modify, and close trades directly from the dashboard
7. **Advanced Analytics**: Provide endpoints for calculating custom metrics, correlation analysis, and portfolio optimization
8. **Multi-Account Support**: Enable viewing data from multiple MT4 accounts simultaneously
9. **Data Export**: Allow exporting market data and trading history in CSV/Excel format
10. **Alerting**: Add endpoints for configuring price alerts and strategy notifications

## Notes *(optional)*

- This specification focuses on the API backend service only. The dashboard (React application) is treated as a separate component with its own development lifecycle.
- The API is designed to be technology-agnostic from the dashboard's perspective - the same endpoints could be consumed by a mobile app or other clients in the future.
- Performance metrics (response times, concurrent users) are based on typical trading dashboard requirements and can be adjusted based on actual load testing results.
- The real-time data streaming approach (WebSocket vs SSE) should be finalized during the planning phase based on deployment infrastructure and browser compatibility requirements.
