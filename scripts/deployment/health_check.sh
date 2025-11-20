#!/bin/bash
# ============================================================================
# RiseTrader Health Check Script
# Monitors all services and reports their status
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.prod.yml"

# Health check endpoints
API_URL="${API_URL:-http://localhost:8003}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://localhost:9200}"
KIBANA_URL="${KIBANA_URL:-http://localhost:5601}"
MLFLOW_URL="${MLFLOW_URL:-http://localhost:5000}"

# ============================================================================
# Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if a service is running
check_service() {
    local service_name=$1
    local container_name=$2

    if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        local status=$(docker inspect --format='{{.State.Status}}' "${container_name}")
        local health=$(docker inspect --format='{{.State.Health.Status}}' "${container_name}" 2>/dev/null || echo "no-healthcheck")

        if [ "$status" == "running" ]; then
            if [ "$health" == "healthy" ] || [ "$health" == "no-healthcheck" ]; then
                log_success "${service_name}: Running (${health})"
                return 0
            else
                log_warning "${service_name}: Running but ${health}"
                return 1
            fi
        else
            log_error "${service_name}: Not running (${status})"
            return 1
        fi
    else
        log_error "${service_name}: Container not found"
        return 1
    fi
}

# Check HTTP endpoint
check_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}

    local response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")

    if [ "$response" == "$expected_code" ]; then
        log_success "${name}: Endpoint accessible (HTTP ${response})"
        return 0
    else
        log_error "${name}: Endpoint not accessible (HTTP ${response})"
        return 1
    fi
}

# Get container stats
get_container_stats() {
    local container_name=$1

    if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        local stats=$(docker stats "${container_name}" --no-stream --format "CPU: {{.CPUPerc}}, Memory: {{.MemUsage}}" 2>/dev/null)
        echo "  ${stats}"
    fi
}

# Check database connection
check_database() {
    log_info "Checking PostgreSQL database..."

    if docker exec risetrader-postgres pg_isready -U postgres > /dev/null 2>&1; then
        log_success "PostgreSQL: Database is ready"

        # Check connection count
        local connections=$(docker exec risetrader-postgres psql -U postgres -d risetrader -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='risetrader';" 2>/dev/null | xargs)
        echo "  Active connections: ${connections}"

        return 0
    else
        log_error "PostgreSQL: Database is not ready"
        return 1
    fi
}

# Check Redis
check_redis() {
    log_info "Checking Redis..."

    if docker exec risetrader-redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis: Responding to PING"

        # Check memory usage
        local memory=$(docker exec risetrader-redis redis-cli INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n ')
        echo "  Memory used: ${memory}"

        return 0
    else
        log_error "Redis: Not responding"
        return 1
    fi
}

# ============================================================================
# Main Health Check
# ============================================================================

main() {
    echo ""
    echo "============================================================================"
    echo "  RiseTrader Production Health Check"
    echo "  $(date)"
    echo "============================================================================"
    echo ""

    local total_checks=0
    local passed_checks=0

    # Check Docker containers
    log_info "Checking Docker containers..."
    echo ""

    services=(
        "PostgreSQL:risetrader-postgres"
        "Redis:risetrader-redis"
        "API:risetrader-api"
        "ML Service:risetrader-ml-service"
        "MLflow:risetrader-mlflow"
        "Prometheus:risetrader-prometheus"
        "Grafana:risetrader-grafana"
        "Elasticsearch:risetrader-elasticsearch"
        "Logstash:risetrader-logstash"
        "Kibana:risetrader-kibana"
        "Dashboard:risetrader-dashboard"
        "Nginx:risetrader-nginx"
    )

    for service in "${services[@]}"; do
        IFS=: read -r name container <<< "$service"
        ((total_checks++))
        if check_service "$name" "$container"; then
            ((passed_checks++))
            get_container_stats "$container"
        fi
    done

    echo ""
    log_info "Checking service connections..."
    echo ""

    # Check database
    ((total_checks++))
    if check_database; then
        ((passed_checks++))
    fi

    # Check Redis
    ((total_checks++))
    if check_redis; then
        ((passed_checks++))
    fi

    echo ""
    log_info "Checking HTTP endpoints..."
    echo ""

    # Check HTTP endpoints
    endpoints=(
        "API Health:${API_URL}/health"
        "API Docs:${API_URL}/docs"
        "Prometheus:${PROMETHEUS_URL}/-/healthy"
        "Grafana:${GRAFANA_URL}/api/health"
        "Elasticsearch:${ELASTICSEARCH_URL}/_cluster/health"
        "Kibana:${KIBANA_URL}/api/status"
        "MLflow:${MLFLOW_URL}/health"
    )

    for endpoint in "${endpoints[@]}"; do
        IFS=: read -r name url <<< "$endpoint"
        ((total_checks++))
        if check_endpoint "$name" "$url"; then
            ((passed_checks++))
        fi
    done

    # Summary
    echo ""
    echo "============================================================================"
    echo "  Health Check Summary"
    echo "============================================================================"
    echo ""

    local percentage=$((passed_checks * 100 / total_checks))

    if [ $percentage -eq 100 ]; then
        log_success "All checks passed: ${passed_checks}/${total_checks} (${percentage}%)"
        echo ""
        echo "✓ RiseTrader is running perfectly!"
    elif [ $percentage -ge 80 ]; then
        log_warning "Most checks passed: ${passed_checks}/${total_checks} (${percentage}%)"
        echo ""
        echo "⚠ RiseTrader is running with some issues"
    else
        log_error "Many checks failed: ${passed_checks}/${total_checks} (${percentage}%)"
        echo ""
        echo "✗ RiseTrader has significant issues"
    fi

    echo ""

    # Exit with appropriate code
    if [ $percentage -ge 80 ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
