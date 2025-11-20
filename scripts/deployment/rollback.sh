#!/bin/bash
# ============================================================================
# RiseTrader Rollback Script
# Rolls back to a previous deployment version
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
BACKUP_DIR="${PROJECT_ROOT}/backups"

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

Rollback RiseTrader to a previous version.

Options:
    -v, --version VERSION    Version tag to rollback to (e.g., 1.0.0)
    -b, --backup BACKUP_FILE Database backup file to restore
    -s, --skip-backup        Skip database backup before rollback
    -h, --help               Show this help message

Examples:
    $0 --version 1.0.0
    $0 --version 1.0.0 --backup backups/risetrader_2025-11-16.dump
    $0 --version latest --skip-backup

EOF
}

# Create backup before rollback
create_backup() {
    log_info "Creating backup before rollback..."

    if [ -f "${SCRIPT_DIR}/backup.sh" ]; then
        bash "${SCRIPT_DIR}/backup.sh" --quick
        log_success "Backup created"
    else
        log_warning "Backup script not found, skipping backup"
    fi
}

# Stop current services
stop_services() {
    log_info "Stopping current services..."

    cd "$PROJECT_ROOT"
    docker-compose -f "$COMPOSE_FILE" down

    log_success "Services stopped"
}

# Restore database from backup
restore_database() {
    local backup_file=$1

    if [ -z "$backup_file" ]; then
        log_warning "No backup file specified, skipping database restore"
        return 0
    fi

    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi

    log_info "Restoring database from backup: ${backup_file}"

    if [ -f "${SCRIPT_DIR}/restore.sh" ]; then
        bash "${SCRIPT_DIR}/restore.sh" --file "$backup_file" --no-confirm
        log_success "Database restored"
    else
        log_error "Restore script not found"
        return 1
    fi
}

# Pull Docker images for specific version
pull_images() {
    local version=$1

    log_info "Pulling Docker images for version: ${version}"

    cd "$PROJECT_ROOT"

    export VERSION="$version"
    docker-compose -f "$COMPOSE_FILE" pull

    log_success "Images pulled"
}

# Start services with specific version
start_services() {
    local version=$1

    log_info "Starting services with version: ${version}"

    cd "$PROJECT_ROOT"

    export VERSION="$version"
    docker-compose -f "$COMPOSE_FILE" up -d

    log_success "Services started"
}

# Verify rollback
verify_rollback() {
    log_info "Verifying rollback..."

    sleep 10  # Wait for services to start

    if [ -f "${SCRIPT_DIR}/health_check.sh" ]; then
        if bash "${SCRIPT_DIR}/health_check.sh"; then
            log_success "Rollback verification passed"
            return 0
        else
            log_error "Rollback verification failed"
            return 1
        fi
    else
        log_warning "Health check script not found, skipping verification"
        return 0
    fi
}

# ============================================================================
# Main Rollback Process
# ============================================================================

main() {
    local version=""
    local backup_file=""
    local skip_backup=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--version)
                version="$2"
                shift 2
                ;;
            -b|--backup)
                backup_file="$2"
                shift 2
                ;;
            -s|--skip-backup)
                skip_backup=true
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

    # Validate version
    if [ -z "$version" ]; then
        log_error "Version is required"
        show_usage
        exit 1
    fi

    echo ""
    echo "============================================================================"
    echo "  RiseTrader Rollback"
    echo "  $(date)"
    echo "============================================================================"
    echo ""
    echo "  Target Version: ${version}"
    echo "  Backup File: ${backup_file:-None}"
    echo "  Skip Backup: ${skip_backup}"
    echo ""
    echo "============================================================================"
    echo ""

    # Confirmation
    if [ "$skip_backup" = false ]; then
        read -p "Are you sure you want to rollback? This will create a backup first. (yes/no): " -r
    else
        read -p "Are you sure you want to rollback WITHOUT backup? (yes/no): " -r
    fi

    if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
        log_info "Rollback cancelled"
        exit 0
    fi

    echo ""

    # Step 1: Create backup (if not skipped)
    if [ "$skip_backup" = false ]; then
        create_backup
        echo ""
    fi

    # Step 2: Stop services
    stop_services
    echo ""

    # Step 3: Restore database (if backup file provided)
    if [ -n "$backup_file" ]; then
        restore_database "$backup_file"
        echo ""
    fi

    # Step 4: Pull images
    pull_images "$version"
    echo ""

    # Step 5: Start services
    start_services "$version"
    echo ""

    # Step 6: Verify
    verify_rollback
    echo ""

    # Summary
    echo "============================================================================"
    echo "  Rollback Complete"
    echo "============================================================================"
    echo ""
    log_success "RiseTrader has been rolled back to version: ${version}"
    echo ""
    echo "  API: http://localhost:8003"
    echo "  Dashboard: http://localhost:3000"
    echo "  Grafana: http://localhost:3001"
    echo ""
    echo "Run './scripts/deployment/health_check.sh' to verify all services"
    echo ""
}

# Run main function
main "$@"
