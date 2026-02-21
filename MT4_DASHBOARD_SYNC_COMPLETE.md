# MT4 Dashboard Sync - Implementation Complete ✅

**Date:** 2025-12-19
**Status:** WORKING
**Issue:** Dashboard showing $0.00 P&L for MT4 positions
**Root Cause:** Field name mismatch between MT4 (camelCase) and Python (snake_case)

---

## Summary

Successfully implemented real-time MT4 position syncing to the dashboard. Positions now update every 60 seconds with correct entry prices and live P&L calculations.

---

## What Was Fixed

### 1. Field Name Mismatch (PRIMARY ISSUE)
**Problem:** MT4 EA sends camelCase fields, Python code expected snake_case
**Impact:** All position data showing as $0.00

| MT4 Field (Actual) | Python Expected (Wrong) | Result |
|--------------------|-------------------------|---------|
| `openPrice` | `open_price` | Always 0.0 |
| `curPrice` | `cur_price` | Always 0.0 |
| `sl` | `stop_loss` | Always null |
| `tp` | `take_profit` | Always null |

**Fix:** Updated `/src/services/mt4_sync_service.py` to use correct MT4 field names:
```python
open_price = float(pos_data.get("openPrice", 0.0))  # Correct!
cur_price = float(pos_data.get("curPrice", 0.0))    # Correct!
stop_loss = pos_data.get("sl")                       # Correct!
take_profit = pos_data.get("tp")                     # Correct!
```

### 2. Missing P&L Calculation
**Problem:** MT4 doesn't send `profit` field, needs to be calculated
**Fix:** Added P&L calculation based on position type:
```python
contract_size = 1000.0  # CrudeOIL contract size
if position_type == "BUY":
    pnl = (cur_price - open_price) * lots * contract_size
else:  # SELL
    pnl = (open_price - cur_price) * lots * contract_size
```

### 3. SQL Enum Type Casting
**Problem:** PostgreSQL enum type `positiontype` requires special handling
**Fix:** Used literal value in SQL instead of parameter:
```python
upsert_sql = text(f"""
    INSERT INTO open_positions (...)
    VALUES (..., '{position_type}'::positiontype, ...)
    ON CONFLICT (number) DO UPDATE SET ...
""")
```

### 4. CORS Configuration
**Problem:** Dashboard on port 3003 couldn't communicate with API
**Fix:** Added port 3003 to `CORS_ORIGINS` in `docker-compose.yml`

### 5. Frontend Null Handling
**Problem:** Dashboard crashed on null/undefined dates
**Fix:** Added null checks in `/dashboard/src/hooks/useFormatters.ts`

---

## Current State

### ✅ Working Features
- **Real-time sync:** Positions update every 60 seconds
- **Correct prices:** Entry prices from MT4 displayed accurately
- **Live P&L:** Calculated from current vs. entry price
- **Auto-update:** UPSERT logic handles new and existing positions
- **Network switching:** Can switch between Local/Remote MT4 servers

### 📊 Test Data
```
Position 24427082:
- Symbol: CrudeOIL
- Type: BUY
- Entry: $58.05
- Size: 0.01 lots
- P&L: -$15.20
- Last Update: 05:39:31 UTC

Position 24427084:
- Symbol: CrudeOIL
- Type: BUY
- Entry: $58.03
- Size: 0.01 lots
- P&L: -$15.10
- Last Update: 05:39:31 UTC
```

---

## Architecture

### MT4 → Python Data Flow
```
MT4 Expert Advisor (MQL4)
    ↓ ZMQ (TCP)
    ↓ {"openPrice": 58.05, "curPrice": 56.53, ...}
MT4 Client (/src/trading/execution/mt4_client.py)
    ↓
MT4 Sync Service (/src/services/mt4_sync_service.py)
    ↓ Field mapping: openPrice → price
    ↓ P&L calculation: (curPrice - openPrice) * lots * 1000
    ↓ UPSERT to PostgreSQL
Database (open_positions table)
    ↓
FastAPI (/src/api/routes/trading.py)
    ↓ JSON: {"price": "58.05", "last_profit": "-15.20"}
React Dashboard (/dashboard/src/pages/Trading.tsx)
    ↓
User sees live positions with P&L
```

### Sync Service Details
- **File:** `/src/services/mt4_sync_service.py`
- **Startup:** FastAPI lifespan in `/src/api/main.py`
- **Interval:** 60 seconds
- **Operations:**
  1. Query MT4 for account info
  2. Query MT4 for open positions
  3. Map camelCase → snake_case
  4. Calculate P&L
  5. UPSERT to database

---

## Files Modified

### Backend
1. `/src/services/mt4_sync_service.py` - NEW: Real-time sync service
2. `/src/api/main.py` - Added MT4 sync to lifespan
3. `/docker-compose.yml` - Added port 3003 to CORS
4. `/src/api/config.py` - Added port 3003 to allowed origins

### Frontend
1. `/dashboard/src/api/endpoints.ts` - Fixed positions response unwrapping
2. `/dashboard/src/hooks/useFormatters.ts` - Added null checks for dates
3. `/dashboard/src/pages/Backtesting.tsx` - Added null check for runData

### Documentation
1. `/MT4_PYTHON_FIELD_MAPPING.md` - NEW: Comprehensive field mapping reference
2. `/MT4_DASHBOARD_SYNC_COMPLETE.md` - NEW: This document

---

## Configuration

### Environment Variables
```bash
# MT4 Connection (in docker-compose.yml)
MT4_HOST=75.154.254.174
MT4_REP_PORT=5555
MT4_PUB_PORT=5556

# CORS (updated)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:3003,http://localhost:5173
```

### Sync Service Settings
```python
# In MT4SyncService class
sync_interval = 60  # seconds
enable_account_sync = True
enable_position_sync = True
```

---

## Testing

### Manual Test Steps
1. Open 2 positions in MT4 demo account
2. Navigate to http://localhost:3003 (dashboard)
3. Click "Trading" page
4. Verify positions show:
   - ✅ Correct entry prices (not $0.00)
   - ✅ Live P&L (not $0.00)
   - ✅ Recent update timestamp
   - ✅ Correct symbol, type, size

### API Test
```bash
curl http://localhost:8003/api/trading/positions | jq '.positions[] | {number, price, last_profit}'
```

Expected output:
```json
{
  "number": "24427082",
  "price": "58.05",
  "last_profit": "-15.20"
}
```

---

## Known Limitations

1. **Contract Size Hardcoded:** Currently using 1000 for CrudeOIL. Need symbol-specific contract sizes.
2. **No Swap/Commission from MT4:** MT4 doesn't send these in position response
3. **Demo Account Only:** Tested on demo, not live account
4. **Manual P&L Calculation:** MT4 doesn't calculate P&L for us

---

## Future Enhancements

### Priority 1 - Critical
- [ ] Add symbol-specific contract size lookup
- [ ] Get swap and commission from MT4
- [ ] Add error recovery for MT4 disconnection

### Priority 2 - Important
- [ ] Add position close tracking
- [ ] Calculate daily P&L aggregates
- [ ] Add position duration calculation
- [ ] Real-time updates via WebSocket (instead of 60s polling)

### Priority 3 - Nice to Have
- [ ] Position history chart
- [ ] P&L alerts/notifications
- [ ] Export position data to CSV

---

## Troubleshooting

### Issue: Positions still showing $0.00
**Check:**
1. Is MT4 EA running and connected?
2. Check MT4 logs for position responses
3. Verify sync service is running: `docker-compose logs api | grep mt4_sync`
4. Check database: `SELECT number, price, last_profit FROM open_positions WHERE simulation = false;`

### Issue: SQL errors in logs
**Common causes:**
- Enum type casting (use `'{value}'::positiontype`)
- Missing unique constraint (use `ON CONFLICT (number)`)
- Parameter binding issues (don't mix `:param` with `$1, $2`)

### Issue: CORS errors
**Check:**
- Dashboard port in CORS_ORIGINS
- Restart API after changing docker-compose.yml
- Browser console for specific origin being blocked

---

## References

- **MT4 Field Mapping:** `/MT4_PYTHON_FIELD_MAPPING.md`
- **MT4 Client Code:** `/src/trading/execution/mt4_client.py`
- **Position Model:** `/src/database/models/open_position.py`
- **MT4 Expert Advisor:** External MT4 terminal

---

## Conclusion

The MT4 dashboard sync is now **fully operational**. Positions update every 60 seconds with correct prices and live P&L calculations. The primary issue was field name mismatches between MT4's camelCase response format and Python's snake_case expectations.

**Key Lesson:** Always check MT4 EA logs to see actual response format instead of assuming field names.

**Status:** ✅ COMPLETE AND TESTED
