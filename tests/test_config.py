"""
Test Configuration

Provides test-specific settings and constants
"""

# Test database settings
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
TEST_REDIS_URL = "redis://localhost:6379/1"

# Test MT4 settings
TEST_MT4_HOST = "localhost"
TEST_MT4_COMMAND_PORT = 5555
TEST_MT4_STREAM_PORT = 5556

# Test risk limits (more permissive for testing)
TEST_MAX_POSITION_SIZE = 10.0
TEST_MAX_DAILY_LOSS = 1000.0
TEST_MAX_OPEN_POSITIONS = 5

# Test timeouts (shorter for faster tests)
TEST_EVENT_TIMEOUT = 5.0
TEST_EXECUTION_TIMEOUT = 5.0
TEST_RETRY_DELAY = 0.5

# Performance targets
REQUIRED_EVENT_THROUGHPUT = 100  # events/sec
REQUIRED_API_LATENCY = 0.2  # 200ms
REQUIRED_SIGNAL_GENERATION_TIME = 0.05  # 50ms
REQUIRED_RISK_VALIDATION_TIME = 0.03  # 30ms
REQUIRED_EXECUTION_TIME = 0.5  # 500ms

# Test data
TEST_SYMBOLS = ["CrudeOIL", "EURUSD", "GOLD", "SP500"]
TEST_TIMEFRAMES = ["1M", "5M", "15M", "1H", "4H", "1D"]

# Mock settings
ENABLE_MOCK_MT4 = True
ENABLE_MOCK_REDIS = True
ENABLE_MOCK_DATABASE = False  # Use real in-memory SQLite
