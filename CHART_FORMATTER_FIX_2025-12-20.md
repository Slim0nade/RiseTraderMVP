# Chart Formatter Fix - 2025-12-20

## Issue

**Error Message:**
```
TypeError: value.toFixed is not a function
```

**When it Occurred:**
- When candle chart preview tried to render
- After fixing the reference error

## Root Cause

The chart's Y-axis and tooltip formatters assumed `value` would always be a number, but when using:

```typescript
<Bar dataKey={(candle: CandleData) => [candle.low, candle.high]} />
```

The value can be an **array** `[low, high]`, not a single number.

## Original Code (❌ Broken)

```typescript
// Y-axis formatter
tickFormatter={(value) => value.toFixed(2)}  // Crashes if value is an array

// Tooltip formatter
formatter={(value: number) => value.toFixed(2)}  // Crashes if value is an array
```

## Fixed Code (✅ Working)

```typescript
// Y-axis formatter - handles both numbers and arrays
tickFormatter={(value) =>
  typeof value === 'number' ? value.toFixed(2) : String(value)
}

// Tooltip formatter - formats arrays as ranges
formatter={(value: any) => {
  if (Array.isArray(value)) {
    return `${value[0]?.toFixed(2)} - ${value[1]?.toFixed(2)}`;
  }
  return typeof value === 'number' ? value.toFixed(2) : String(value);
}}
```

## What This Does

**For Y-axis:**
- If number: Shows "71.50"
- If array/other: Converts to string

**For Tooltip:**
- If array: Shows "71.50 - 72.30" (low - high range)
- If number: Shows "71.50"
- If other: Converts to string

## File Modified

**File:** `/dashboard/src/components/backtesting/IntelligentDatePicker.tsx`
- Lines 409, 422-427: Added type checking before calling `.toFixed()`

## Why This Happened

Recharts Bar components can accept either:
1. Single number: `dataKey="close"`
2. Array of numbers: `dataKey={(item) => [item.low, item.high]}`

We're using option 2 to show price ranges (low to high), so formatters must handle arrays.

## Testing

✅ Chart renders without errors
✅ Tooltip shows "Low - High" range when hovering
✅ Y-axis labels display correctly

## Status

✅ **Fixed and Ready**
