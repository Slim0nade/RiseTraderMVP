-- ============================================================================
-- RiseTrader Database Initialization Script
-- Creates database and basic schema if not exists
-- ============================================================================

-- Create database if not exists (handled by Docker env var, but kept for reference)
-- CREATE DATABASE risetrader;

-- Connect to the database
\c risetrader;

-- Create extensions (handled in extensions.sql, but basic ones here)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create schema for separating concerns (optional)
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE risetrader TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA trading TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA analytics TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA monitoring TO postgres;

-- Create monitoring user (optional, for Prometheus postgres_exporter)
-- DO $$
-- BEGIN
--     IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'exporter') THEN
--         CREATE USER exporter WITH PASSWORD 'exporter_password';
--     END IF;
-- END $$;
-- GRANT CONNECT ON DATABASE risetrader TO exporter;
-- GRANT USAGE ON SCHEMA public, trading, analytics, monitoring TO exporter;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'RiseTrader database initialized successfully';
END $$;
