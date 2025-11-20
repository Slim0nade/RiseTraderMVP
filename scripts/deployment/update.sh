#!/bin/bash
# ============================================================================
# RiseTrader Update Script
# Updates RiseTrader to the latest version with zero downtime
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

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Update RiseTrader to a new version.

Options:
    -v, --version VERSION    Version to update to (default: latest)
    --no-backup              Skip backup before update
    --force                  Force update even if version is the same
    -h, --help               Show this help message

Examples:
    $0
    $0 --version 1.1.0
    $0 --no-backup --force

EOF
}

# Create backup before update
create_backup() {
    log_info "Creating backup before update..."

    if [ -f "${SCRIPT_DIR}/backup.sh" ]; then
        bash "${SCRIPT_DIR}/backup.sh" --quick
        log_success "Backup created"
    else
        log_warning "Backup script not found, skipping backup"
    fi
}

# Get current version
get_current_version() {
    local version=$(docker inspect --format='{{index .Config.Labels "version"}}' risetrader-api 2>/dev/null || echo "unknown")
    echo "$version"
}

# Pull latest images
pull_images() {
    local version=$1

    log_info "Pulling Docker images for version: ${version}"

    cd "$PROJECT_ROOT"

    export VERSION="$version"
    docker-compose -f "$COMPOSE_FILE" pull

    log_success "Images pulled"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."

    docker-compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head

    log_success "Migrations completed"
}

# Update services with rolling update
update_services() {
    local version=$1

    log_info "Updating services to version: ${version}"

    cd "$PROJECT_ROOT"

    export VERSION="$version"

    # Update API with rolling restart
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps --scale api=3 api
    sleep 10
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps --scale api=2 api

    # Update other services
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps ml-service
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps dashboard

    # Update monitoring (can be updated without disruption)
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps prometheus grafana

    log_success "Services updated"
}

# Verify update
verify_update() {
    log_info "Verifying update..."

    sleep 15  # Wait for services to stabilize

    if [ -f "${SCRIPT_DIR}/health_check.sh" ]; then
        if bash "${SCRIPT_DIR}/health_check.sh"; then
            log_success "Update verification passed"
            return 0
        else
            log_error "Update verification failed"
            return 1
        fi
    else
        log_warning "Health check script not found, skipping verification"
        return 0
    fi
}

# Cleanup old images
cleanup() {
    log_info "Cleaning up old Docker images..."

    docker image prune -f --filter "label=maintainer=RiseTrader Team"

    log_success "Cleanup completed"
}

# ============================================================================
# Main Update Process
# ============================================================================

main() {
    local version="latest"
    local no_backup=false
    local force=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--version)
                version="$2"
                shift 2
                ;;
            --no-backup)
                no_backup=true
                shift
                ;;
            --force)
                force=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    echo ""
    echo "============================================================================"
    echo "  RiseTrader Update"
    echo "  $(date)"
    echo "============================================================================"
    echo ""

    local current_version=$(get_current_version)
    echo "  Current Version: ${current_version}"
    echo "  Target Version: ${version}"
    echo ""
    echo "============================================================================"
    echo ""

    # Check if update is needed
    if [ "$current_version" == "$version" ] && [ "$force" = false ]; then
        log_info "Already running version ${version}. Use --force to update anyway."
        exit 0
    fi

    # Confirmation
    read -p "Continue with update? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
        log_info "Update cancelled"
        exit 0
    fi

    echo ""

    # Step 1: Create backup (if not skipped)
    if [ "$no_backup" = false ]; then
        create_backup
        echo ""
    fi

    # Step 2: Pull images
    pull_images "$version"
    echo ""

    # Step 3: Run migrations
    run_migrations
    echo ""

    # Step 4: Update services
    update_services "$version"
    echo ""

    # Step 5: Verify
    if verify_update; then
        echo ""

        # Step 6: Cleanup
        cleanup
        echo ""

        # Summary
        echo "============================================================================"
        echo "  Update Complete"
        echo "============================================================================"
        echo ""
        log_success "RiseTrader has been updated to version: ${version}"
        echo ""
        echo "  API: http://localhost:8003"
        echo "  Dashboard: http://localhost:3000"
        echo "  Grafana: http://localhost:3001"
        echo ""
    else
        echo ""
        log_error "Update verification failed. Consider rolling back."
        echo ""
        echo "To rollback, run:"
        echo "  ./scripts/deployment/rollback.sh --version ${current_version}"
        echo ""
        exit 1
    fi
}

# Run main function
main "$@"
