# Data Model: MT4 Integration

**Feature**: MT4 Integration
**Date**: 2025-11-20
**Phase**: 1 - Design & Contracts

## Overview

This document defines the entity models, relationships, and validation rules for the MT4 Integration feature. The data model supports multiple EA connections, order tracking, portfolio risk state, and audit trails.

---

## Entity Relationship Diagram

```
┌─────────────────────┐
│  MT4Connection      │
│  (EA Registry)      │
├─────────────────────┤
│ PK id               │
│    ea_id (unique)   │
│    magic_number     │◄──────┐
│    rep_port         │       │
│    pub_port         │       │
│    symbol           │       │
│    status           │       │
│    encryption_keys  │       │
└─────────────────────┘       │
         │                     │
         │ 1:N                 │
         ▼                     │
┌─────────────────────┐       │
│  MT4Order           │       │
│  (Order Tracking)   │       │
├─────────────────────┤       │
│ PK id               │       │
│ FK magic_number     │───────┘
│    ticket_number    │
│    order_id (UUID)  │
│    symbol           │
│    direction        │
│    volume           │
│    order_type       │
│    status           │
│    submitted_at     │
│    confirmed_at     │
│    executed_at      │
└─────────────────────┘
         │
         │ 1:1 (optional)
         ▼
┌─────────────────────┐
│  MT4Position        │
│  (Open Positions)   │
├─────────────────────┤
│ PK id               │
│ FK order_id         │
│    ticket_number    │
│    magic_number     │
│    symbol           │
│    direction        │
│    volume           │
│    open_price       │
│    current_price    │
│    unrealized_pnl   │
│    open_time        │
│    stop_loss        │
│    take_profit      │
└─────────────────────┘

┌─────────────────────┐
│ PortfolioRiskState  │
│ (Cached in Redis)   │
├─────────────────────┤
│    total_equity     │
│    total_margin     │
│    margin_level     │
│    open_positions   │
│    exposure_map     │
│    last_updated     │
└─────────────────────┘
```

---

## Entity Definitions

### 1. MT4Connection

**Purpose**: Registry of Expert Advisor connections, tracking connection state and configuration.

**Table**: `mt4_connections`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique connection identifier |
| ea_id | VARCHAR(50) | UNIQUE, NOT NULL | Human-readable EA identifier (e.g., "crude_oil_ea_1") |
| magic_number | INTEGER | UNIQUE, NOT NULL | MT4 magic number (100000-999999) |
| rep_port | INTEGER | NOT NULL | ZMQ REP socket port (5555 + offset) |
| pub_port | INTEGER | NOT NULL | ZMQ PUB socket port (5556 + offset) |
| symbol | VARCHAR(20) | NOT NULL | Primary trading symbol for this EA |
| status | ENUM | NOT NULL | ACTIVE, INACTIVE, ERROR, RECONNECTING |
| mt4_server_host | VARCHAR(100) | NOT NULL | MT4 server IP/hostname |
| encryption_enabled | BOOLEAN | NOT NULL, DEFAULT TRUE | Whether CurveZMQ is enabled |
| client_public_key | VARCHAR(64) | NULL | Z85-encoded client public key |
| server_public_key | VARCHAR(64) | NULL | Z85-encoded server public key |
| last_heartbeat | TIMESTAMP | NULL | Last successful ping/pong timestamp |
| error_count | INTEGER | DEFAULT 0 | Consecutive error count for health monitoring |
| created_at | TIMESTAMP | NOT NULL | Connection registration time |
| updated_at | TIMESTAMP | NOT NULL | Last status update time |

**Indexes**:
- `idx_mt4_magic_number` on `magic_number` (frequent lookups)
- `idx_mt4_status` on `status` (for health monitoring queries)

**Validation Rules**:
- `magic_number` BETWEEN 100000 AND 999999
- `rep_port` BETWEEN 5000 AND 65535
- `pub_port` BETWEEN 5000 AND 65535
- `rep_port` != `pub_port`
- `status` IN ('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING')

**SQLAlchemy Model**:

```python
class MT4Connection(Base):
    __tablename__ = "mt4_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ea_id = Column(String(50), unique=True, nullable=False)
    magic_number = Column(Integer, unique=True, nullable=False)
    rep_port = Column(Integer, nullable=False)
    pub_port = Column(Integer, nullable=False)
    symbol = Column(String(20), nullable=False)
    status = Column(Enum('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING', name='connection_status'), nullable=False)
    mt4_server_host = Column(String(100), nullable=False, default='75.154.254.174')
    encryption_enabled = Column(Boolean, nullable=False, default=True)
    client_public_key = Column(String(64), nullable=True)
    server_public_key = Column(String(64), nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders = relationship("MT4Order", back_populates="connection")

    @validates('magic_number')
    def validate_magic_number(self, key, value):
        if not (100000 <= value <= 999999):
            raise ValueError("Magic number must be between 100000 and 999999")
        return value
```

---

### 2. MT4Order

**Purpose**: Tracks order lifecycle from submission to execution/rejection.

**Table**: `mt4_orders`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique order identifier |
| order_id | VARCHAR(36) | UNIQUE, NOT NULL | External UUID for API/agent reference |
| magic_number | INTEGER | FK, NOT NULL | References mt4_connections.magic_number |
| ticket_number | INTEGER | UNIQUE, NULL | MT4 ticket number (NULL until confirmed) |
| symbol | VARCHAR(20) | NOT NULL | Trading symbol (e.g., "CrudeOIL") |
| direction | ENUM | NOT NULL | BUY, SELL |
| volume | DECIMAL(10,2) | NOT NULL | Order volume in lots |
| order_type | ENUM | NOT NULL | MARKET, LIMIT, STOP, BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP |
| limit_price | DECIMAL(10,5) | NULL | Limit price for pending orders |
| stop_loss | DECIMAL(10,5) | NULL | Stop loss price |
| take_profit | DECIMAL(10,5) | NULL | Take profit price |
| status | ENUM | NOT NULL | PENDING, CONFIRMED, EXECUTED, REJECTED, CANCELLED |
| execution_price | DECIMAL(10,5) | NULL | Actual execution price |
| required_margin | DECIMAL(12,2) | NULL | Estimated margin requirement |
| error_message | TEXT | NULL | Error details if rejected |
| submitted_at | TIMESTAMP | NOT NULL | When order was submitted to MT4 |
| confirmed_at | TIMESTAMP | NULL | When MT4 confirmed receipt |
| executed_at | TIMESTAMP | NULL | When order was filled |
| correlation_id | VARCHAR(36) | NOT NULL | UUID for tracing across services |

**Indexes**:
- `idx_mt4_order_magic` on `magic_number` (EA-specific queries)
- `idx_mt4_order_ticket` on `ticket_number` (MT4 lookups)
- `idx_mt4_order_status` on `status` (active order queries)
- `idx_mt4_order_correlation` on `correlation_id` (tracing)

**Validation Rules**:
- `volume` > 0
- `direction` IN ('BUY', 'SELL')
- `status` IN ('PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED')
- `order_type` IN ('MARKET', 'LIMIT', 'STOP', 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP')
- `confirmed_at` >= `submitted_at` (if not NULL)
- `executed_at` >= `confirmed_at` (if not NULL)

**State Transitions**:

```
PENDING → CONFIRMED → EXECUTED
   ↓          ↓
REJECTED  CANCELLED
```

**SQLAlchemy Model**:

```python
class MT4Order(Base):
    __tablename__ = "mt4_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String(36), unique=True, nullable=False)
    magic_number = Column(Integer, ForeignKey('mt4_connections.magic_number'), nullable=False)
    ticket_number = Column(Integer, unique=True, nullable=True)
    symbol = Column(String(20), nullable=False)
    direction = Column(Enum('BUY', 'SELL', name='order_direction'), nullable=False)
    volume = Column(Numeric(10, 2), nullable=False)
    order_type = Column(Enum('MARKET', 'LIMIT', 'STOP', 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP', name='order_type'), nullable=False)
    limit_price = Column(Numeric(10, 5), nullable=True)
    stop_loss = Column(Numeric(10, 5), nullable=True)
    take_profit = Column(Numeric(10, 5), nullable=True)
    status = Column(Enum('PENDING', 'CONFIRMED', 'EXECUTED', 'REJECTED', 'CANCELLED', name='order_status'), nullable=False)
    execution_price = Column(Numeric(10, 5), nullable=True)
    required_margin = Column(Numeric(12, 2), nullable=True)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    correlation_id = Column(String(36), nullable=False)

    # Relationships
    connection = relationship("MT4Connection", back_populates="orders")
    position = relationship("MT4Position", uselist=False, back_populates="order")
```

---

### 3. MT4Position

**Purpose**: Represents open positions in MT4 with current P&L tracking.

**Table**: `mt4_positions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, NOT NULL | Unique position identifier |
| order_id | UUID | FK, NULL | References mt4_orders.id (NULL for manual positions) |
| ticket_number | INTEGER | UNIQUE, NOT NULL | MT4 position ticket |
| magic_number | INTEGER | NOT NULL | Magic number identifying EA |
| symbol | VARCHAR(20) | NOT NULL | Trading symbol |
| direction | ENUM | NOT NULL | BUY, SELL |
| volume | DECIMAL(10,2) | NOT NULL | Position size in lots |
| open_price | DECIMAL(10,5) | NOT NULL | Position open price |
| current_price | DECIMAL(10,5) | NOT NULL | Current market price (updated) |
| unrealized_pnl | DECIMAL(12,2) | NOT NULL | Current P&L |
| stop_loss | DECIMAL(10,5) | NULL | Stop loss level |
| take_profit | DECIMAL(10,5) | NULL | Take profit level |
| open_time | TIMESTAMP | NOT NULL | When position was opened |
| last_updated | TIMESTAMP | NOT NULL | Last price update time |

**Indexes**:
- `idx_mt4_pos_ticket` on `ticket_number` (primary lookup)
- `idx_mt4_pos_magic` on `magic_number` (EA positions)
- `idx_mt4_pos_symbol` on `symbol` (symbol exposure queries)

**Validation Rules**:
- `volume` > 0
- `direction` IN ('BUY', 'SELL')
- `unrealized_pnl` calculated as: (current_price - open_price) * volume * contract_size (for BUY)

**SQLAlchemy Model**:

```python
class MT4Position(Base):
    __tablename__ = "mt4_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey('mt4_orders.id'), nullable=True)
    ticket_number = Column(Integer, unique=True, nullable=False)
    magic_number = Column(Integer, nullable=False)
    symbol = Column(String(20), nullable=False)
    direction = Column(Enum('BUY', 'SELL', name='position_direction'), nullable=False)
    volume = Column(Numeric(10, 2), nullable=False)
    open_price = Column(Numeric(10, 5), nullable=False)
    current_price = Column(Numeric(10, 5), nullable=False)
    unrealized_pnl = Column(Numeric(12, 2), nullable=False)
    stop_loss = Column(Numeric(10, 5), nullable=True)
    take_profit = Column(Numeric(10, 5), nullable=True)
    open_time = Column(DateTime, nullable=False)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    order = relationship("MT4Order", back_populates="position")
```

---

### 4. PortfolioRiskState

**Purpose**: Aggregated risk metrics across all EAs (cached in Redis).

**Redis Key**: `portfolio:risk:state`

**Data Structure** (JSON):

```json
{
  "total_equity": "50000.00",
  "total_margin_used": "35000.00",
  "margin_level": "142.86",
  "total_open_positions": 15,
  "exposure_by_symbol": {
    "CrudeOIL": "25000.00",
    "EURUSD": "10000.00",
    "GBPUSD": "5000.00"
  },
  "exposure_by_ea": {
    "100001": "12000.00",
    "100002": "18000.00",
    "100003": "5000.00"
  },
  "last_updated": "2025-11-20T10:30:00Z"
}
```

**Pydantic Model**:

```python
class PortfolioRiskState(BaseModel):
    total_equity: Decimal
    total_margin_used: Decimal
    margin_level: Decimal
    total_open_positions: int
    exposure_by_symbol: Dict[str, Decimal]
    exposure_by_ea: Dict[str, Decimal]  # magic_number -> margin
    last_updated: datetime

    @property
    def is_margin_critical(self) -> bool:
        """Check if margin level is below safety threshold"""
        return self.margin_level < Decimal('120.00')  # 120% is warning level

    @property
    def available_margin_pct(self) -> Decimal:
        """Calculate available margin as percentage"""
        if self.total_equity == 0:
            return Decimal('0')
        return ((self.total_equity - self.total_margin_used) / self.total_equity) * 100
```

**TTL**: 60 seconds (refreshed on every position update)

---

## Migration Scripts

### Initial Migration: Create Tables

```python
# alembic/versions/001_create_mt4_tables.py

def upgrade():
    # Create mt4_connections table
    op.create_table(
        'mt4_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ea_id', sa.String(50), nullable=False),
        sa.Column('magic_number', sa.Integer(), nullable=False),
        sa.Column('rep_port', sa.Integer(), nullable=False),
        sa.Column('pub_port', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'ERROR', 'RECONNECTING', name='connection_status'), nullable=False),
        sa.Column('mt4_server_host', sa.String(100), nullable=False),
        sa.Column('encryption_enabled', sa.Boolean(), nullable=False),
        sa.Column('client_public_key', sa.String(64), nullable=True),
        sa.Column('server_public_key', sa.String(64), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('error_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ea_id'),
        sa.UniqueConstraint('magic_number')
    )

    # Create indexes
    op.create_index('idx_mt4_magic_number', 'mt4_connections', ['magic_number'])
    op.create_index('idx_mt4_status', 'mt4_connections', ['status'])

    # Create mt4_orders table
    # ... (similar structure)

    # Create mt4_positions table
    # ... (similar structure)

def downgrade():
    op.drop_table('mt4_positions')
    op.drop_table('mt4_orders')
    op.drop_table('mt4_connections')
```

---

## Data Access Patterns

### Common Queries

1. **Get Active EA Connections**:
```sql
SELECT * FROM mt4_connections WHERE status = 'ACTIVE';
```

2. **Get EA Orders by Magic Number**:
```sql
SELECT * FROM mt4_orders
WHERE magic_number = ?
AND status IN ('PENDING', 'CONFIRMED')
ORDER BY submitted_at DESC;
```

3. **Calculate Symbol Exposure**:
```sql
SELECT symbol, SUM(volume * open_price) as exposure
FROM mt4_positions
WHERE direction = 'BUY'
GROUP BY symbol;
```

4. **Get Portfolio Margin Usage**:
```sql
SELECT magic_number, SUM(required_margin) as margin_used
FROM mt4_orders
WHERE status = 'EXECUTED'
GROUP BY magic_number;
```

---

## Audit Trail

All state changes are logged to `audit_log` table (existing in RiseTrader) with:
- `entity_type`: 'mt4_connection', 'mt4_order', 'mt4_position'
- `entity_id`: Primary key of affected entity
- `action`: 'CREATE', 'UPDATE', 'DELETE'
- `old_value`: JSON snapshot before change
- `new_value`: JSON snapshot after change
- `timestamp`: When change occurred
- `actor`: Service/agent that made the change

---

**Data Model Complete**: Ready for contract definitions and quickstart guide.
