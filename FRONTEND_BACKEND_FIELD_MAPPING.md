# Frontend ↔ Backend Field Mapping Reference

**CRITICAL:** The frontend Position interface uses different field names than the backend API. This document maps all fields to prevent display issues.

Last Updated: 2025-12-19

---

## The Problem

The dashboard was showing $0.00 for all P&L values despite the backend API returning correct data. Root cause: **field name mismatch** between frontend TypeScript types and backend API responses.

---

## Position Fields Mapping

| Frontend Field (`Position` interface) | Backend Field (`PositionResponse` API) | Type | Notes |
|--------------------------------------|----------------------------------------|------|-------|
| `id` | `id` | string | ✅ Same |
| `symbol` | `symbol` | string | ✅ Same |
| `action` | `type` | 'BUY' \| 'SELL' | ❌ **Different field name** |
| `entry_price` | `price` | number | ❌ **Different field name** |
| `current_price` | N/A | number | ⚠️ **Missing from API!** Using `price` for now |
| `quantity` | `size` | number | ❌ **Different field name** |
| `unrealized_pnl` | `last_profit` | number | ❌ **Different field name** |
| `stop_loss` | `stop_loss` | number \| undefined | ✅ Same |
| `take_profit` | `take_profit` | number \| undefined | ✅ Same |
| `entry_time` | `last_update` | string | ⚠️ Using `last_update` as workaround |
| `strategy_name` | `last_strategy` | string | ❌ **Different field name** |

---

## Example API Response

```json
{
  "positions": [
    {
      "id": 1779,
      "number": "24427082",
      "type": "BUY",
      "size": "0.01",
      "symbol": "CrudeOIL",
      "price": "58.05",
      "stop_loss": null,
      "take_profit": null,
      "commission": "0.00",
      "last_profit": "-15.20",
      "last_update": "2025-12-19T05:39:31.123456",
      "last_strategy": "MT4_LIVE",
      "simulation": false
    }
  ]
}
```

---

## Frontend Transformation Code

Location: `/dashboard/src/api/endpoints.ts` (lines 40-74)

```typescript
getOpenPositions: async () => {
  // API returns PositionResponse with different field names
  interface ApiPosition {
    id: string;
    number: string;
    type: 'BUY' | 'SELL';
    size: number;
    symbol: string;
    price: number;
    stop_loss?: number;
    take_profit?: number;
    commission: number;
    last_profit?: number;
    last_update: string;
    last_strategy: string;
    simulation: boolean;
  }

  const response = await apiClient.get<{ positions: ApiPosition[] }>('/api/trading/positions');

  // Transform API response to match frontend Position interface
  return response.positions.map((apiPos): Position => ({
    id: apiPos.id,
    symbol: apiPos.symbol,
    action: apiPos.type,                    // Map type → action
    entry_price: apiPos.price,              // Map price → entry_price
    current_price: apiPos.price,            // TODO: API missing current_price
    quantity: apiPos.size,                  // Map size → quantity
    unrealized_pnl: apiPos.last_profit || 0, // Map last_profit → unrealized_pnl
    stop_loss: apiPos.stop_loss,
    take_profit: apiPos.take_profit,
    entry_time: apiPos.last_update,         // Map last_update → entry_time
    strategy_name: apiPos.last_strategy,    // Map last_strategy → strategy_name
  }));
},
```

---

## Common Pitfalls

### ❌ WRONG - Using frontend field names directly
```typescript
// This returns undefined because API doesn't have 'unrealized_pnl'
const pnl = response.positions[0].unrealized_pnl;  // undefined!
```

### ✅ CORRECT - Map backend fields to frontend
```typescript
// Transform API response
const pnl = apiPos.last_profit;  // -15.20
```

### ❌ WRONG - Expecting current_price from API
```typescript
// API doesn't send current_price yet
const current = apiPos.current_price;  // undefined!
```

### ✅ CORRECT - Use entry price as placeholder
```typescript
// Use entry price until API is updated to send current price
const current = apiPos.price;  // 58.05
```

---

## Related Files

- **Frontend Type Definitions:** `/dashboard/src/types/index.ts` (lines 2-14)
- **Frontend API Client:** `/dashboard/src/api/endpoints.ts` (lines 40-74)
- **Backend API Response Model:** `/src/api/models/trading_models.py` (lines 110-148)
- **Backend Trading Routes:** `/src/api/routes/trading.py` (lines 97-149)
- **MT4 Sync Service:** `/src/services/mt4_sync_service.py`

---

## Testing Checklist

When adding new position-related features:

- [ ] Check frontend Position interface in types/index.ts
- [ ] Check backend PositionResponse model in trading_models.py
- [ ] Add field mapping in endpoints.ts transformation layer
- [ ] Update this document with new field mappings
- [ ] Test with real API data (not mock data)
- [ ] Verify dashboard displays correct values

---

## Known Issues & Future Work

### Issue 1: Missing current_price from API
**Impact:** Dashboard can't show real-time price updates separate from entry price
**Workaround:** Using entry price (`price`) for both entry_price and current_price
**Fix Required:** Update MT4 sync service to also store current market price

### Issue 2: Using last_update for entry_time
**Impact:** entry_time shows last update timestamp, not actual position open time
**Workaround:** Using last_update field
**Fix Required:** Add open_time field to database and API response

### Issue 3: Field name inconsistency across codebase
**Impact:** Confusing for developers, prone to bugs
**Long-term Fix:** Standardize on either snake_case or camelCase across entire stack

---

## Resolution Timeline

**2025-12-19 05:30 UTC:** Issue discovered - Dashboard showing $0.00 P&L
**2025-12-19 05:45 UTC:** Backend sync service fixed (MT4 camelCase → Python mapping)
**2025-12-19 06:00 UTC:** API confirmed returning correct data
**2025-12-19 06:15 UTC:** Frontend transformation layer added
**Status:** ✅ FIXED - Dashboard now displays correct P&L values

---

## Key Lesson

**Always verify field names at API boundaries!**

TypeScript interfaces don't enforce runtime checks. If the API returns different field names than the interface expects, the fields will be `undefined` at runtime with no compile-time error.

**Solution:** Create explicit transformation layers when field names don't match between backend and frontend.
