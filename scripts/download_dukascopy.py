#!/usr/bin/env python3
"""
Legacy Dukascopy downloader - now redirects to data_sync.py

Use data_sync.py for the full featured data sync service:
    python scripts/data_sync.py status         # Check status
    python scripts/data_sync.py                # Sync all
    python scripts/data_sync.py --symbol CrudeOIL  # Sync specific
    python scripts/data_sync.py --force-days 7     # Re-download last 7 days
"""
import sys
from pathlib import Path

print("=" * 60)
print("⚠️  This script is deprecated!")
print("=" * 60)
print()
print("Use the new data sync service instead:")
print()
print("  # Check data status and gaps")
print("  python scripts/data_sync.py status")
print()
print("  # Sync all symbols (auto-detect gaps)")
print("  python scripts/data_sync.py")
print()
print("  # Sync specific symbol")
print("  python scripts/data_sync.py --symbol CrudeOIL")
print()
print("  # Force re-download last N days")
print("  python scripts/data_sync.py --force-days 7")
print()
print("  # Dry run (show what would be done)")
print("  python scripts/data_sync.py --dry-run")
print()
print("=" * 60)

# Forward to sync service
if len(sys.argv) > 1:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    import asyncio
    from src.data.sync import main
    
    # Map old args to new
    if sys.argv[1] == "full":
        sys.argv = [sys.argv[0]]  # Just run sync all
    
    asyncio.run(main())
