# MT4 ↔ Python Field Name Mapping Reference

**CRITICAL:** MT4 uses camelCase, Python uses snake_case. This document maps all field names to prevent mismatches.

Last Updated: 2025-12-19

---

## Account Info Fields

| MT4 Response (camelCase) | Python Expected (snake_case) | Type | Description |
|--------------------------|------------------------------|------|-------------|
| `balance` | `balance` | float | Account balance |
| `equity` | `equity` | float | Account equity |
| `margin` | `margin` | float | Used margin |
| `freeMargin` | `free_margin` | float | Free margin available |
| `marginLevel` | `margin_level` | float | Margin level percentage |

**Example MT4 Response:**
```json
{
  "status": "OK",
  "account_info": {
    "balance": 12866.80,
    "equity": 12823.70,
    "margin": 84.16,
    "freeMargin": 12739.54,
    "marginLevel": 15237.65
  }
}
```

---

## Position Fields

| MT4 Response (camelCase) | Python Expected (snake_case) | Type | Description |
|--------------------------|------------------------------|------|-------------|
| `ticket` | `number` (DB field) | string | Position ticket number |
| `symbol` | `symbol` | string | Trading symbol |
| `type` | `type` | string | "BUY" or "SELL" |
| `lots` | `size` (DB field) | float | Position size in lots |
| `openPrice` | `price` (DB field) | float | Entry/open price |
| `curPrice` | N/A (calc P&L) | float | Current market price |
| `sl` | `stop_loss` | float | Stop loss price |
| `tp` | `take_profit` | float | Take profit price |
| `commission` | `commission` | float | Commission paid |
| N/A | `last_profit` (calculated) | float | Current P&L |

**Example MT4 Response:**
```json
{
  "status": "OK",
  "positions": [
    {
      "ticket": 24427082,
      "symbol": "CrudeOIL",
      "type": "BUY",
      "lots": 0.01,
      "openPrice": 58.04500,
      "curPrice": 56.52500,
      "sl": 0.00000,
      "tp": 0.00000
    }
  ]
}
```

**Python Mapping Code:**
```python
# MT4 returns camelCase, map to snake_case
open_price = float(pos_data.get("openPrice", 0.0))  # NOT "open_price"
cur_price = float(pos_data.get("curPrice", 0.0))    # NOT "cur_price"
lots = float(pos_data.get("lots", 0.0))
position_type = pos_data.get("type", "BUY").upper()
stop_loss = pos_data.get("sl")                       # NOT "stop_loss"
take_profit = pos_data.get("tp")                     # NOT "take_profit"

# Calculate P&L manually (MT4 doesn't send it)
contract_size = 1000.0  # CrudeOIL contract size
if position_type == "BUY":
    pnl = (cur_price - open_price) * lots * contract_size
else:  # SELL
    pnl = (open_price - cur_price) * lots * contract_size
```

---

## Database Column Mapping

| MT4 Field | Python Var | DB Column | Type |
|-----------|------------|-----------|------|
| `ticket` | `ticket` | `number` | varchar |
| `lots` | `lots` | `size` | numeric |
| `openPrice` | `open_price` | `price` | numeric |
| (calculated) | `pnl` | `last_profit` | numeric |
| `sl` | `stop_loss` | `stop_loss` | numeric |
| `tp` | `take_profit` | `take_profit` | numeric |

---

## Common Pitfalls

### ❌ WRONG - Using snake_case for MT4 fields
```python
price = pos_data.get("open_price", 0.0)  # Returns 0.0 - field doesn't exist!
```

### ✅ CORRECT - Using camelCase for MT4 fields
```python
price = pos_data.get("openPrice", 0.0)   # Returns actual price
```

### ❌ WRONG - Expecting `profit` from MT4
```python
pnl = pos_data.get("profit", 0.0)  # MT4 doesn't send this!
```

### ✅ CORRECT - Calculate P&L from openPrice and curPrice
```python
open_price = float(pos_data.get("openPrice", 0.0))
cur_price = float(pos_data.get("curPrice", 0.0))
pnl = (cur_price - open_price) * lots * contract_size  # For BUY
```

---

## Testing Checklist

When adding new MT4 integration code:

- [ ] Check MT4 EA logs for actual response format
- [ ] Use camelCase for MT4 response fields
- [ ] Use snake_case for Python/database fields
- [ ] Add field mapping in this document
- [ ] Test with real MT4 data (not mock data)
- [ ] Verify database inserts work correctly
- [ ] Check dashboard displays correct values

---

## Related Files

- **MT4 Sync Service:** `/src/services/mt4_sync_service.py`
- **MT4 Client:** `/src/trading/execution/mt4_client.py`
- **Position Model:** `/src/database/models/open_position.py`
- **Trading Routes:** `/src/api/routes/trading.py`
