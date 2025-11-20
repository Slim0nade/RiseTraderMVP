-- ============================================================================
-- RiseTrader PostgreSQL Extensions
-- Time-series and performance extensions for trading data
-- ============================================================================

\c risetrader;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Time-series data optimization (TimescaleDB)
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Full-text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Statistics and analytics
CREATE EXTENSION IF NOT EXISTS tablefunc;

-- Performance monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Encryption functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Log extensions loaded
DO $$
DECLARE
    ext RECORD;
BEGIN
    RAISE NOTICE 'Installed PostgreSQL Extensions:';
    FOR ext IN
        SELECT extname, extversion
        FROM pg_extension
        WHERE extname NOT IN ('plpgsql')
        ORDER BY extname
    LOOP
        RAISE NOTICE '  - % (version %)', ext.extname, ext.extversion;
    END LOOP;
END $$;
