#!/usr/bin/env python3
"""
RiseTrader Data Sync - Simple wrapper script.

Usage:
    # Check current data status
    python scripts/data_sync.py status
    
    # Sync all enabled symbols (auto-detect gaps)
    python scripts/data_sync.py
    
    # Sync specific symbol
    python scripts/data_sync.py --symbol CrudeOIL
    
    # Dry run (show what would be downloaded)
    python scripts/data_sync.py --dry-run
    
    # Force re-download last N days
    python scripts/data_sync.py --force-days 7

Docker:
    docker exec -it risetrader-api python scripts/data_sync.py
    docker exec -it risetrader-api python scripts/data_sync.py status
    docker exec -it risetrader-api python scripts/data_sync.py --symbol CrudeOIL

Cron Examples:
    # Daily sync at 6am (after markets close)
    0 6 * * * docker exec risetrader-api python scripts/data_sync.py >> /var/log/risetrader-sync.log 2>&1
    
    # Weekly full re-sync on Sunday
    0 0 * * 0 docker exec risetrader-api python scripts/data_sync.py --force-days 7 >> /var/log/risetrader-sync.log 2>&1
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Run the sync module
if __name__ == "__main__":
    import asyncio
    from src.data.sync import main
    asyncio.run(main())
