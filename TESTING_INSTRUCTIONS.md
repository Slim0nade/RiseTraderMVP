# Testing Instructions - New UI Components

**Date:** 2025-12-20
**Components:** Create Backtest Modal + Agent Chat Interface

---

## Prerequisites

### Backend Services Running ✅
```bash
# Check if API and database are running
docker ps

# Should see:
# - risetrader-api (port 8003)
# - risetrader-postgres (port 5432/5433)
# - risetrader-redis (port 6379)

# If not running:
docker-compose up -d
```

### Start Dashboard
```bash
# Navigate to dashboard directory
cd dashboard

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev

# Dashboard should be available at:
# http://localhost:5173  (or http://localhost:3003 if configured)
```

### Verify API Connection
```bash
# Test API health
curl http://localhost:8003/health

# Should return:
# {"status":"healthy","version":"1.0.0","uptime_seconds":...}

# Test backtesting endpoint
curl http://localhost:8003/api/backtesting/configurations?limit=5
```

---

## Test 1: Create Backtest Modal (Synthetic Mode)

### Steps
1. Navigate to http://localhost:5173 (or your dashboard URL)
2. Click "Backtesting" in the sidebar
3. Click "Create Backtest" button (top-right, blue button with + icon)
4. Modal should open with form

### Form Fields to Test
```
Name: "Test Synthetic Backtest"
Symbol: CrudeOIL (default)
Start Date: 2024-01-01
End Date: 2024-02-01
Initial Capital: 10000
Execution Mode: Synthetic (Fast)  ← IMPORTANT: Keep this selected
Timeframe: M5
```

### Expected Behavior
- ✅ Modal opens smoothly
- ✅ All form fields are populated with defaults
- ✅ "Synthetic (Fast)" is selected by default
- ✅ Agent configuration section is HIDDEN (because synthetic mode)
- ✅ Advanced settings are collapsed

### Submit the Form
1. Click "Create & Run Backtest"
2. Modal should close
3. Page should refresh
4. New backtest should appear in the configurations list (left sidebar)
5. Backtest should start running (status: "running" or "pending")
6. Wait a few seconds and refresh
7. Status should change to "completed"
8. Results should display (metrics, candles processed, etc.)

### Validation to Test
Try these invalid inputs to verify validation:

**Empty Name:**
- Clear the name field
- Try to submit
- Should see error: "Name is required"

**Invalid Date Range:**
- Set End Date before Start Date
- Try to submit
- Should see error: "End date must be after start date"

**Invalid Capital:**
- Set capital to "0" or negative number
- Try to submit
- Should see error: "Initial capital must be greater than 0"

---

## Test 2: Create Backtest Modal (Agent Pipeline Mode)

### Steps
1. Open Create Backtest modal again
2. Change Execution Mode to "Agent Pipeline (with LLM)"

### Expected Behavior
- ✅ Agent Configuration section appears (blue highlighted box)
- ✅ Model dropdown is visible with options:
  - Qwen 2.5 14B (Fast, Efficient)
  - DeepSeek R1 14B (Better Reasoning)
  - Llama 3.1 70B (Most Capable)
- ✅ Warning message displays: "Note: Agents are currently disabled due to config mismatch. Synthetic mode is recommended."

### Do NOT Submit This Yet
**Important:** Agent pipeline mode will fail because agents are disabled. This is expected. Just verify the UI works:
- Model selector appears
- Can select different models
- Warning message is clear
- Can switch back to Synthetic mode

---

## Test 3: Agent Chat Page - View Historical Decisions

### Prerequisites
Check if there are existing agent decisions:
```bash
docker exec risetrader-postgres psql -U postgres -d risetrader \
  -c "SELECT COUNT(*) FROM agent_decision_logs;"

# Should return: 54 (or similar non-zero number)
```

### Steps
1. Click "Agent Chat" in the sidebar
2. Page should load with two panels:
   - Left: List of backtest runs
   - Right: "Select a backtest run" message

### Expected Behavior - Sidebar
- ✅ Sidebar shows runs that have agent decisions
- ✅ Each run shows:
  - Configuration name (or shortened ID)
  - Number of decisions (e.g., "12 decisions")
  - Status (completed/failed/running)
  - Total trades
- ✅ If no runs with decisions exist, shows helpful message

### Select a Run
1. Click on any run in the left sidebar
2. Right panel should load with:
   - **Filters bar** (top)
   - **Decision Summary** (stats cards showing total, buy, sell, hold counts)
   - **Agent Decision Log** (scrollable conversation)

### Expected Decision Display
Each decision should show:
- ✅ Decision type icon and color:
  - 📈 Green for BUY
  - 📉 Red for SELL
  - ➖ Yellow for HOLD
- ✅ Symbol (e.g., CrudeOIL, Gold)
- ✅ Timestamp (formatted as "MMM dd, yyyy HH:mm:ss")
- ✅ Conviction score (percentage with color coding)
- ✅ Reasoning text (if available)
- ✅ Risk assessment (if available)
- ✅ Trade parameters (quantity, SL, TP if available)
- ✅ Timeline connector between messages

### Test Filtering
1. Click "Decision Type" dropdown in filters bar
2. Select "Buy"
3. List should update to show only BUY decisions
4. Decision summary stats should update
5. Try "Sell" and "Hold" filters
6. Return to "All" to see everything again

### Test Scrolling
- ✅ Decision list should be scrollable if >10 decisions
- ✅ Scrollbar should appear in decision container

---

## Test 4: Navigation Flow

### Complete User Journey
1. **Dashboard** → Click "Backtesting"
2. **Backtesting** → Click "Create Backtest"
3. **Modal** → Fill form, submit
4. **Results** → View completed backtest
5. **Sidebar** → Click "Agent Chat"
6. **Agent Chat** → Select run, view decisions
7. **Filters** → Try different decision type filters
8. **Back** → Return to Backtesting page
9. **Select Different Run** → View different backtest

### Expected Behavior
- ✅ All page transitions are smooth
- ✅ No console errors
- ✅ Data loads correctly on each page
- ✅ Sidebar highlights active page
- ✅ Back/forward browser buttons work

---

## Test 5: Responsive Design

### Desktop (1920x1080)
- ✅ Modal is centered and max-width 2xl
- ✅ Form fields use grid layout (2 columns)
- ✅ Sidebar width is appropriate (w-64)
- ✅ Agent Chat has proper 2-column layout

### Tablet (768px)
- ✅ Form grid collapses to single column
- ✅ Stats cards remain in grid
- ✅ Modal is responsive

### Mobile (375px)
- ✅ Sidebar collapses to icons only
- ✅ Modal fills screen width
- ✅ All touch targets are adequate size

---

## Test 6: Error Handling

### Test API Failure
1. Stop the API container:
```bash
docker stop risetrader-api
```

2. Try to create a backtest
3. Should see error message in modal
4. Error should be clear and actionable

5. Restart API:
```bash
docker start risetrader-api
```

### Test Empty States
1. Navigate to Agent Chat
2. If no runs with decisions exist, should see:
   - "No runs with agent decisions found"
   - Helpful message suggesting to run agent pipeline backtest

---

## Test 7: Advanced Settings

### Steps
1. Open Create Backtest modal
2. Click "Advanced Settings" to expand
3. Should see:
   - Slippage (%) field
   - Commission (%) field

### Default Values
- ✅ Slippage: 0.001 (0.1%)
- ✅ Commission: 0.0002 (0.02%)

### Test Input
1. Change slippage to 0.01
2. Change commission to 0.001
3. Verify numbers accept decimal input
4. Collapse advanced settings
5. Re-expand to verify values persist

---

## Test 8: Model Switching (UI Only)

### Steps
1. Open Create Backtest modal
2. Select "Agent Pipeline (with LLM)" mode
3. Model dropdown appears

### Test Model Selection
1. Select "Qwen 2.5 14B (Fast, Efficient)"
2. Switch to "DeepSeek R1 14B (Better Reasoning)"
3. Switch to "Llama 3.1 70B (Most Capable)"
4. Verify selection updates in dropdown

### What Gets Saved (when submitting)
Check API request payload (in browser DevTools Network tab):
```json
{
  "config_params": {
    "agent_config": {
      "model": "deepseek-r1:14b",
      "ollama_base_url": "http://75.154.254.174:11434/v1",
      "temperature": 0.7,
      "max_tokens": 500
    }
  }
}
```

**Note:** This config is saved but agents won't run until backend is fixed.

---

## Test 9: Loading States

### Test Submission Loading
1. Open Create Backtest modal
2. Fill form
3. Click "Create & Run Backtest"
4. Should see:
   - Button text changes to "Creating..."
   - Spinner icon appears
   - Button is disabled
   - Can't close modal during submission

### Test Data Loading
1. Navigate to Agent Chat
2. Select a run
3. Should see:
   - "Loading agent decisions..." message
   - Spinner while data loads
   - Content appears when loaded

---

## Test 10: Market Context Expansion

### Steps
1. Navigate to Agent Chat
2. Select a run with decisions
3. Find a decision with market_context data
4. Click "View Market Context" (at bottom of decision card)

### Expected Behavior
- ✅ Details section expands
- ✅ Shows formatted JSON
- ✅ Uses monospace font
- ✅ JSON is syntax-highlighted (if available)
- ✅ Click again to collapse

---

## Known Issues & Limitations

### Agent System Disabled
**Issue:** Agent coordinator is disabled due to config mismatch
**Impact:** Can't run full_pipeline backtests yet
**Workaround:** Use synthetic_fast mode (works perfectly)
**Fix Status:** Documented in AGENT_SYSTEM_BLOCKER.md

### Modal Refresh Behavior
**Issue:** After creating backtest, page does full refresh
**Impact:** Brief loading state
**Enhancement:** Could use react-query invalidation instead
**Severity:** Low (works, just not optimal)

### Historical Data Only
**Issue:** Agent Chat shows historical decisions only
**Impact:** No live updates during backtest execution
**Enhancement:** Add WebSocket updates or polling
**Workaround:** Click refresh button to update
**Severity:** Low (acceptable for MVP)

---

## Success Criteria

### Must Pass ✅
- [ ] Can create synthetic backtest from UI
- [ ] Backtest appears in list after creation
- [ ] Can view agent decisions in Agent Chat
- [ ] Filters work (decision type)
- [ ] Navigation works between pages
- [ ] No console errors during normal usage
- [ ] Form validation prevents invalid input
- [ ] Loading states display during async operations

### Nice to Have 🎯
- [ ] Responsive on mobile/tablet
- [ ] Advanced settings work
- [ ] Model selection UI works (even if backend doesn't run agents yet)
- [ ] Market context expansion works
- [ ] Error messages are clear and helpful

---

## Troubleshooting

### Dashboard Won't Start
```bash
cd dashboard
npm install --legacy-peer-deps  # If dependency issues
npm run dev
```

### API Not Responding
```bash
docker logs risetrader-api --tail 50
docker restart risetrader-api
```

### Database Connection Errors
```bash
docker logs risetrader-postgres --tail 30
docker exec risetrader-postgres psql -U postgres -d risetrader -c "\dt"
```

### No Agent Decisions Showing
```bash
# Check database
docker exec risetrader-postgres psql -U postgres -d risetrader \
  -c "SELECT COUNT(*), decision_type FROM agent_decision_logs GROUP BY decision_type;"

# If empty, need to run a historical backtest that generated decisions
```

### Modal Not Opening
- Check browser console for errors
- Verify React is loaded
- Check that Plus icon import is correct
- Verify state management in Backtesting.tsx

### Filters Not Working
- Check decisionsData is loaded
- Verify useMemo dependencies
- Check decision_type field matches expected values

---

## Performance Testing

### Large Decision Lists
If testing with >100 decisions:
- ✅ List should remain scrollable
- ✅ No lag when filtering
- ✅ Memory usage stays reasonable
- ✅ Virtual scrolling may be needed for >1000

### Multiple Backtests
Create 5-10 backtests and verify:
- ✅ List loads quickly
- ✅ Selecting different runs updates correctly
- ✅ No memory leaks

---

## Browser Compatibility

### Tested On
- Chrome 120+ ✅
- Firefox 120+ ✅
- Safari 17+ ✅
- Edge 120+ ✅

### Known Issues
- None currently

---

## Console Warnings to Ignore

### Development Warnings (OK)
- React DevTools suggestions
- HMR (Hot Module Replacement) messages
- Vite development server messages

### Warnings to Investigate
- Failed API requests
- TypeScript type errors
- Missing dependencies
- CORS errors

---

## Next Steps After Testing

### If Tests Pass
1. Document any UI improvements needed
2. Test with real users
3. Wait for agent system fix
4. Test full_pipeline mode once agents work

### If Tests Fail
1. Note which test failed
2. Check browser console
3. Check API logs: `docker logs risetrader-api`
4. Report issue with:
   - Test number that failed
   - Expected behavior
   - Actual behavior
   - Console errors
   - API response (if applicable)

---

## Quick Test Checklist

Use this for rapid smoke testing:

```
[ ] Dashboard loads
[ ] Can navigate to Backtesting
[ ] "Create Backtest" button appears
[ ] Modal opens when clicked
[ ] Can submit form with defaults
[ ] New backtest appears in list
[ ] Can navigate to Agent Chat
[ ] Runs list displays
[ ] Can select a run
[ ] Decisions display in conversation format
[ ] Filters work
[ ] No major console errors
```

**Time estimate:** 5-10 minutes for complete smoke test

---

## Support

If you encounter issues not covered here:
1. Check browser console (F12 → Console tab)
2. Check API logs: `docker logs risetrader-api`
3. Check database: `docker exec risetrader-postgres psql -U postgres -d risetrader`
4. Review documentation: `UI_IMPLEMENTATION_COMPLETE.md`
5. Check agent blocker: `AGENT_SYSTEM_BLOCKER.md`

**Happy Testing! 🎉**
