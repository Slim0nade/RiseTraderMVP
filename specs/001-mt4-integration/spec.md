# Feature Specification: MT4 Integration

**Feature Branch**: `001-mt4-integration`
**Created**: 2025-11-20
**Status**: Draft
**Input**: User description: "Implement the MT4 integration"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send Market Orders to MT4 (Priority: P1)

The trading system needs to send buy and sell orders to the MetaTrader 4 platform when trading signals are generated. When an autonomous agent determines that a trade should be executed, the system must communicate this decision to MT4 and receive confirmation that the order was successfully placed.

**Why this priority**: This is the core capability that enables any automated trading. Without the ability to send orders to MT4, the platform cannot execute trades and has no value. This is the foundation upon which all other MT4 integration features are built.

**Independent Test**: Can be fully tested by configuring a test trading signal, triggering the execution, and verifying that a corresponding order appears in MT4 with correct parameters (symbol, volume, type, price limits). Delivers the ability to automate trade execution.

**Acceptance Scenarios**:

1. **Given** the system has generated a BUY signal for CrudeOIL with position size 0.1 lots, **When** the execution agent sends the order, **Then** a BUY order for CrudeOIL 0.1 lots appears in MT4 within 500 milliseconds
2. **Given** the system has generated a SELL signal with stop-loss and take-profit levels, **When** the order is sent, **Then** MT4 shows the order with the correct stop-loss and take-profit values
3. **Given** an order is sent successfully, **When** the system receives MT4's response, **Then** the system records the MT4 order ticket number and confirmation timestamp

---

### User Story 2 - Receive Order Status Updates (Priority: P1)

The trading system needs to receive real-time updates about order status from MT4, including when orders are filled, partially filled, rejected, or cancelled. This ensures the system always has an accurate view of the current trading state and can make informed decisions.

**Why this priority**: Without order status updates, the system is blind to what's actually happening in MT4. It cannot track positions, calculate P&L, or make risk management decisions. This is equally critical to sending orders.

**Independent Test**: Can be tested by manually placing orders in MT4 (or via the system) and verifying that the system receives and correctly processes all status changes. Delivers real-time awareness of trading state.

**Acceptance Scenarios**:

1. **Given** an order has been sent to MT4, **When** MT4 fills the order, **Then** the system receives a fill notification within 100 milliseconds including fill price and timestamp
2. **Given** an open position exists in MT4, **When** the position is closed (manually or automatically), **Then** the system receives the closure notification with final P&L
3. **Given** MT4 rejects an order due to insufficient margin, **When** the rejection occurs, **Then** the system receives the rejection reason and updates the order status accordingly
4. **Given** multiple orders are being processed, **When** status updates arrive, **Then** each update is correctly matched to its corresponding order using the ticket number

---

### User Story 3 - Stream Live Market Data (Priority: P2)

The trading system needs to receive real-time price quotes (bid, ask, timestamp) from MT4 for all actively traded symbols. This market data feeds the signal generation and forecasting systems, enabling them to make decisions based on current market conditions.

**Why this priority**: While critical for live trading, market data streaming can initially be simulated or sourced from alternative feeds during development. Order execution (P1 stories) can be tested with delayed or cached price data. However, for production live trading, this becomes essential.

**Independent Test**: Can be tested by subscribing to symbol price feeds from MT4 and verifying that bid/ask updates arrive with timestamps and match MT4's displayed prices. Delivers real-time market awareness.

**Acceptance Scenarios**:

1. **Given** the system subscribes to CrudeOIL price feed, **When** prices change in MT4, **Then** the system receives tick updates with bid, ask, and timestamp within 50 milliseconds
2. **Given** multiple symbols are subscribed (CrudeOIL, EURUSD, GBPUSD), **When** any price updates, **Then** the system receives updates for all subscribed symbols independently
3. **Given** the market data stream is active, **When** the connection is interrupted, **Then** the system detects the interruption within 5 seconds and attempts reconnection
4. **Given** market data is streaming, **When** tick rate exceeds expected volume, **Then** the system handles high-frequency updates without message loss or delays exceeding 100 milliseconds

---

### User Story 4 - Query Account Information (Priority: P3)

The trading system needs to query MT4 for current account information including balance, equity, margin level, open positions, and order history. This enables risk management, performance monitoring, and audit capabilities.

**Why this priority**: Account information queries are important for comprehensive system operation but not blocking for basic order execution. The system can operate with cached or estimated account state initially. This becomes increasingly important as the system matures.

**Independent Test**: Can be tested by requesting account information from MT4 and verifying that returned data matches MT4's account display. Delivers comprehensive account visibility.

**Acceptance Scenarios**:

1. **Given** the system needs current account balance, **When** an account info request is sent, **Then** MT4 responds within 200 milliseconds with balance, equity, margin, and free margin
2. **Given** positions are open in MT4, **When** the system queries open positions, **Then** the response includes all positions with symbol, volume, open price, current P&L, and ticket number
3. **Given** the system needs historical data, **When** requesting order history for the past 24 hours, **Then** MT4 returns all completed orders with timestamps, fill prices, and P&L
4. **Given** account queries are frequent, **When** making multiple requests, **Then** responses remain consistent and no request takes longer than 500 milliseconds

---

### User Story 5 - Manage Multiple Expert Advisors (Priority: P2)

The trading system needs to connect to and coordinate multiple Expert Advisors (EAs) running simultaneously in MT4, each executing different trading strategies. The system must track which orders belong to which EA (via magic numbers), aggregate risk across all EAs, and ensure that portfolio-level risk limits are not exceeded by the combined activity of all strategies.

**Why this priority**: Supporting multiple EAs is essential for running a diversified trading portfolio with multiple strategies. However, single-EA operation can be validated first, making this lower priority than basic execution capabilities. This becomes critical before production deployment with real strategies.

**Independent Test**: Can be tested by launching 3 EAs in MT4 with different magic numbers, sending orders from each, and verifying that the system correctly attributes orders to their respective EAs and calculates cumulative risk. Delivers multi-strategy portfolio management.

**Acceptance Scenarios**:

1. **Given** 3 EAs are running with magic numbers 100001, 100002, and 100003, **When** each EA places an order, **Then** the system correctly identifies which EA placed each order using the magic number
2. **Given** multiple EAs are active, **When** querying open positions, **Then** the system returns all positions grouped by EA/magic number
3. **Given** EA1 has 2 open positions using 40% margin and EA2 has 1 position using 35% margin, **When** calculating portfolio risk, **Then** the system reports 75% total margin usage across all EAs
4. **Given** portfolio risk limit is 80% margin usage, **When** EA3 attempts to open a position requiring 20% margin, **Then** the system blocks the order to prevent exceeding the 80% limit
5. **Given** multiple EAs are streaming market data, **When** price updates arrive, **Then** each EA receives updates only for its subscribed symbols without interference

---

### Edge Cases

- What happens when MT4 connection is lost while orders are in-flight?
- How does the system handle MT4 responding with "market closed" for a symbol?
- What if MT4 accepts an order but returns an error during execution (insufficient margin, invalid stops)?
- How does the system behave when MT4 price quotes become stale or stop updating?
- What happens if MT4 responds with partial fills or multiple fills for a single order?
- How does the system handle MT4 server maintenance windows or broker disconnections?
- What if message queues overflow during high-frequency trading periods?
- How does the system distinguish between network issues vs MT4 platform issues?
- What happens if one EA crashes while others continue running?
- How does the system handle magic number conflicts if two EAs are accidentally assigned the same magic number?
- What if portfolio risk limits are reached but one EA has an emergency close order that needs to execute?
- How does the system handle the case where MT4 terminal is restarted and all EA connections need to re-establish?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST establish a persistent bidirectional communication channel with MT4 platform
- **FR-002**: System MUST send market orders (BUY/SELL) to MT4 with symbol, volume, order type, and optional stop-loss/take-profit parameters
- **FR-003**: System MUST receive order confirmation from MT4 including unique order ticket number and execution timestamp within 500 milliseconds
- **FR-004**: System MUST receive real-time order status updates (pending, filled, partial, rejected, cancelled) from MT4
- **FR-005**: System MUST receive real-time position updates including current P&L for all open positions
- **FR-006**: System MUST stream live market data (bid, ask, timestamp) for subscribed symbols with latency under 50 milliseconds
- **FR-007**: System MUST query account information (balance, equity, margin, free margin) on demand
- **FR-008**: System MUST query open positions list with details (symbol, volume, open price, current price, P&L)
- **FR-009**: System MUST query order history for specified time periods
- **FR-010**: System MUST detect connection failures and automatically attempt reconnection with exponential backoff
- **FR-011**: System MUST encrypt all communication with MT4 using CurveZMQ encryption with key pairs (client secret key, client public key, server public key)
- **FR-012**: System MUST handle MT4 error responses (insufficient margin, invalid parameters, market closed) and propagate errors to calling agents
- **FR-013**: System MUST maintain message ordering for critical operations (order submission, position updates)
- **FR-014**: System MUST implement timeout handling for all MT4 requests with configurable timeout values (default: 5 seconds for commands, 10 seconds for queries)
- **FR-015**: System MUST log all MT4 communication (requests, responses, errors) with timestamps and correlation IDs for audit purposes
- **FR-016**: System MUST support multiple Expert Advisor (EA) connections simultaneously, with up to 100 EAs per MT4 terminal instance
- **FR-017**: System MUST assign and track unique magic numbers for each EA to prevent order interference between different strategies
- **FR-018**: System MUST aggregate risk metrics across all connected EAs to calculate cumulative portfolio exposure
- **FR-019**: System MUST enforce portfolio-level risk limits that consider the combined positions and margin usage of all EAs
- **FR-020**: System MUST identify orders by both magic number and ticket number to support EA-specific order management

### Key Entities

- **Expert Advisor (EA)**: Represents a trading strategy instance running in MT4, containing unique EA identifier, magic number, assigned symbol(s), connection ports (REP/PUB), encryption keys, and active status
- **Trading Order**: Represents an order to be executed on MT4, containing symbol, direction (BUY/SELL), volume, order type (market/limit/stop), optional stop-loss, optional take-profit, magic number, and timestamp
- **Order Confirmation**: Represents MT4's response to an order submission, containing success/failure status, MT4 ticket number, magic number, execution price, execution timestamp, and any error messages
- **Position**: Represents an open trading position in MT4, containing ticket number, magic number, symbol, direction, volume, open price, current price, unrealized P&L, open timestamp
- **Market Tick**: Represents a real-time price update from MT4, containing symbol, bid price, ask price, and timestamp
- **Account Status**: Represents current MT4 account state, containing balance, equity, margin used, free margin, margin level percentage, and number of open positions
- **Portfolio Risk State**: Represents aggregated risk across all EAs, containing total exposure by symbol, cumulative margin usage, number of active EAs, total open positions, and combined unrealized P&L
- **Connection State**: Represents the communication link status with MT4, containing connection status (connected/disconnected/reconnecting), last successful message timestamp, error count, and reconnection attempts

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Orders sent to MT4 are confirmed within 500 milliseconds for 99% of submissions under normal market conditions
- **SC-002**: Market data updates are received with end-to-end latency under 50 milliseconds for 95% of ticks
- **SC-003**: Connection failures are detected within 5 seconds and reconnection is attempted automatically
- **SC-004**: System successfully handles at least 100 concurrent orders without message loss or ordering violations
- **SC-005**: All MT4 communication is encrypted and no plaintext trading messages are transmitted over the network
- **SC-006**: Order status updates are received and processed within 100 milliseconds of MT4 state changes
- **SC-007**: Account information queries return complete data within 200 milliseconds for 99% of requests
- **SC-008**: System operates continuously for 24-hour periods without connection loss requiring manual intervention
- **SC-009**: Error rates (connection failures, timeout errors, invalid responses) remain below 0.1% under normal operating conditions
- **SC-010**: All trading operations are auditable through complete request/response logs with microsecond timestamps

## Assumptions

1. **MT4 Server Location**: MT4 server is located at IP address 75.154.254.174 as documented in project files
2. **ZMQ Socket Architecture**: Each EA uses dual ZMQ sockets - REP socket (port 5555 + EA offset) for request/response commands, PUB socket (port 5556 + EA offset) for real-time market data streaming
3. **Message Format**: JSON-formatted messages for all commands and responses between trading system and MT4 EAs
4. **MT4 Availability**: Assumes MT4 platform and broker connection are available during configured trading hours (24/5 for forex/commodities with specific session windows)
5. **Network Reliability**: Assumes reasonably stable network connection with internet access between trading system and MT4 server
6. **Order Types**: MT4 supports standard order types (OP_BUY, OP_SELL for market orders; OP_BUYLIMIT, OP_SELLLIMIT, OP_BUYSTOP, OP_SELLSTOP for pending orders)
7. **Real-time Capabilities**: MT4 EAs push real-time updates via PUB socket including OHLCV data, technical indicators (MA, RSI, MACD, Bollinger Bands, ATR, SAR, VWAP, Fibonacci levels), and trading signals
8. **Concurrent Operations**: MT4 can handle multiple simultaneous requests (orders, queries, subscriptions) from the trading system across multiple EAs
9. **Error Reporting**: MT4 provides GetLastError() codes and structured error messages in JSON responses
10. **Historical Data**: MT4 provides access to recent order history via get_account_info and historical price data via iTime/iOpen/iHigh/iLow/iClose functions
11. **Magic Number Range**: Each EA is assigned a unique magic number in the range 100000-999999 to identify its orders
12. **EA Command Set**: Existing EA prototype supports commands including test_connection, login, loadPair, create_instant_order, create_pending_order, close_position, get_open_positions, get_account_info, get_symbols, getOHLCV, and technical indicator retrieval

## Dependencies

- MT4 platform must be installed, configured, and connected to broker account
- MT4 server must have integration capabilities enabled (likely requires Expert Advisor or custom script running in MT4)
- Network connectivity must exist between trading system and MT4 server (IP: 75.154.254.174)
- Encryption keys or VPN configuration must be provisioned before production deployment (security requirement)

## Out of Scope

- Historical data backfill beyond recent order history (handled by separate data ingestion system)
- MT4 platform installation, configuration, or troubleshooting
- Broker account setup or funding operations
- Trading strategy logic or signal generation (handled by agent system)
- Risk management decision-making (handled by RiskManager agents)
- Custom indicator calculations within MT4 (system relies on externally calculated indicators)
- MT4 platform upgrades or migration to MT5
- Multi-broker support (initially limited to single MT4 connection)
- Manual trading operations through MT4 GUI (system assumes full automation)
