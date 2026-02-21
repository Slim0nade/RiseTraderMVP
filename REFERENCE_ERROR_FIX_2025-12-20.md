# Reference Error Fix - 2025-12-20

## Issue

**Error Message:**
```
ReferenceError: Cannot access 'validation' before initialization
```

**When it Occurred:**
- When opening the "Create Backtest" modal
- Dashboard crashed with error overlay

## Root Cause

Variable declaration order issue in `IntelligentDatePicker.tsx`:

```typescript
// ❌ WRONG ORDER - Using validation before it's defined
const candlePreview = useQuery({
  enabled: validation.isValid,  // Line 93 - Using validation
  ...
});

const validation = useMemo(() => {  // Line 98 - Defining validation
  ...
}, [availability, startDate, endDate]);
```

This violates JavaScript's Temporal Dead Zone (TDZ) rule - you cannot access a variable before it's declared, even with hoisting.

## Fix Applied

Reordered the code to define `validation` BEFORE using it:

```typescript
// ✅ CORRECT ORDER
// 1. Data availability query
const availability = useQuery({ ... });

// 2. Validation useMemo (uses availability)
const validation = useMemo(() => {
  ...
}, [availability, startDate, endDate]);

// 3. Candle preview query (uses validation)
const candlePreview = useQuery({
  enabled: validation.isValid,  // Now validation is already defined
  ...
});
```

## File Modified

**File:** `/dashboard/src/components/backtesting/IntelligentDatePicker.tsx`

**Changes:**
- Moved `validation` useMemo from line 98 to line 85 (before candle preview query)
- Candle preview query now at line 149 (after validation is defined)

## Why This Happened

When I added the candle chart preview feature, I inserted the query in the wrong location - before the validation logic it depends on. This is a common mistake when adding new features to existing code.

## Testing

✅ **Verified:** Modal now opens without errors
✅ **Verified:** Chart preview loads correctly
✅ **Verified:** All other features still work

## Lesson Learned

When adding code that depends on other variables:
1. Always check variable declaration order
2. Dependencies must be declared before use
3. React hooks order matters but within that, regular variables must follow JS scoping rules

## Status

✅ **Fixed and Deployed**
