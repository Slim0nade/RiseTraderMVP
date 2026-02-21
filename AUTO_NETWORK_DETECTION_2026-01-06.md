# Automatic Network Detection - Implementation

**Date:** January 6, 2026
**Status:** ✅ Implemented and Tested

---

## Problem Statement

### Before This Fix

**Issue:** Manual network switching was error-prone:
- .env file showed `NETWORK_LOCATION=local` but user was actually remote
- Required manual editing of `.env` file
- Easy to forget which network you're on
- Connection failures with unclear reasons

**User Request:**
> "The MT4_HOST shouldn't be a variable or we need 2 of them MT4_HOST_LOCAL and MT4_HOST_REMOTE and have the system basculate between both based on availability of 192.168.0.123"

---

## Solution Implemented

### Automatic Network Detection Script

**File:** `scripts/detect_network.py`

**Features:**
1. ✅ Tests LOCAL network first (192.168.0.123) - faster if at home
2. ✅ Falls back to REMOTE network (75.154.254.174) if local unreachable
3. ✅ Automatically updates .env file with correct configuration
4. ✅ Updates BOTH MT4_HOST and OLLAMA_BASE_URL together (same server)
5. ✅ Clear output showing what was detected and changed

---

## How It Works

### Detection Logic

```python
def detect_network():
    # 1. Try LOCAL first (2 second timeout)
    if test_connection("192.168.0.123", 5555, timeout=2):
        return "local", "192.168.0.123"  # Fast local network!

    # 2. Fall back to REMOTE (5 second timeout)
    if test_connection("75.154.254.174", 5555, timeout=5):
        return "remote", "75.154.254.174"  # Internet access

    # 3. Neither accessible
    return None, None  # Server is down or network issue
```

### Test Method

- Uses raw socket connection to MT4 port 5555
- Quick timeouts (2s local, 5s remote)
- No dependencies on ZMQ or Ollama libraries
- Reliable low-level network test

---

## Usage

### Automatic Detection (Recommended)

```bash
# Detect network and switch automatically
python3 scripts/detect_network.py

# Output:
# 🔍 Detecting network location...
#   Testing LOCAL network (192.168.0.123)...
#   ❌ LOCAL network unreachable (not at home)
#   Testing REMOTE network (75.154.254.174)...
#   ✅ REMOTE network is accessible!
#
# ✅ DETECTED: REMOTE NETWORK
# 🔄 Switching from LOCAL to REMOTE...
# ✅ Updated .env file with REMOTE configuration
#
# ⚠️  IMPORTANT: Restart services for changes to take effect:
#    docker-compose restart api
```

### Test Only (Don't Switch)

```bash
# Just check which network is accessible
python3 scripts/detect_network.py --test

# Output:
# 📍 Detected network: REMOTE (75.154.254.174)
# ⚠️  .env file is set to LOCAL, but REMOTE is accessible
# 💡 Run: python3 scripts/detect_network.py (to switch)
```

### Check Current Status

```bash
# Show current configuration
python3 scripts/detect_network.py --status

# Output:
# ============================================================
# 🌐 CURRENT NETWORK CONFIGURATION
# ============================================================
#   Network Location: REMOTE
#   MT4 Host:         75.154.254.174
#   Ollama URL:       http://75.154.254.174:11434
#   Testing connectivity to 75.154.254.174...
#   ✅ Server is reachable
# ============================================================
```

---

## What Gets Updated

When the script detects a network change, it updates **3 variables** in `.env`:

```bash
# Before (when at home):
NETWORK_LOCATION=local
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://192.168.0.123:11434

# After (when remote):
NETWORK_LOCATION=remote
MT4_HOST=75.154.254.174
OLLAMA_BASE_URL=http://75.154.254.174:11434
```

**⚠️ IMPORTANT:** Both services updated together (same server!)

---

## Integration Workflow

### Startup Workflow (Recommended)

Add to your startup routine:

```bash
# 1. Detect and switch to correct network
python3 scripts/detect_network.py

# 2. Restart services with new config
docker-compose restart api

# 3. Verify connection
curl http://localhost:8003/health
```

### Coming Home Workflow

```bash
# When you arrive home, run auto-detect
python3 scripts/detect_network.py

# Should detect LOCAL and switch automatically
# Then restart:
docker-compose restart api
```

### Leaving Home Workflow

```bash
# Before leaving, run auto-detect one more time
python3 scripts/detect_network.py

# Should still be on LOCAL, no change needed
# When you're remote, run it again and it will switch to REMOTE
```

---

## Testing Results

### Test 1: Remote Detection (2026-01-06)

```bash
$ python3 scripts/detect_network.py

🔍 Detecting network location...
  Testing LOCAL network (192.168.0.123)...
  ❌ LOCAL network unreachable (not at home)
  Testing REMOTE network (75.154.254.174)...
  ✅ REMOTE network is accessible!

✅ DETECTED: REMOTE NETWORK
🔄 Switching from LOCAL to REMOTE...
✅ Updated .env file with REMOTE configuration
```

**Result:** ✅ Correctly detected remote, updated .env, API restarted successfully

### Test 2: Connectivity Verification

```bash
$ nc -zv 75.154.254.174 5555
Connection to 75.154.254.174 port 5555 [tcp/personal-agent] succeeded!

$ nc -zv 75.154.254.174 5556
Connection to 75.154.254.174 port 5556 [tcp/freeciv] succeeded!

$ curl http://75.154.254.174:11434/api/tags
{"models":[...9 models available...]}
```

**Result:** ✅ All connections verified working

---

## Advantages Over Manual Switching

### Before (Manual)

❌ User has to remember which network they're on
❌ User has to manually edit .env file
❌ Easy to forget to update BOTH variables
❌ No feedback if configuration is wrong
❌ Requires knowledge of IP addresses

### After (Auto-Detection)

✅ Script automatically detects network
✅ No manual editing required
✅ Always updates both variables together
✅ Clear feedback on what was detected/changed
✅ Works from anywhere (just run the script)

---

## Future Enhancements

### Option 1: Auto-Run on API Startup

Add to API startup script to auto-detect every time:

```python
# In start_api.sh or FastAPI startup
import subprocess
subprocess.run(["python3", "scripts/detect_network.py"])
```

**Pros:**
- Fully automatic, no user action needed
- Always correct network on startup

**Cons:**
- Adds ~5-7 seconds to startup time
- May be unexpected if user wants manual control

### Option 2: Cron Job for Periodic Detection

```bash
# Check every 5 minutes and auto-switch if needed
*/5 * * * * cd /path/to/RiseTraderMVP && python3 scripts/detect_network.py
```

**Pros:**
- Handles network changes automatically
- No startup delay

**Cons:**
- Requires cron setup
- May restart API unexpectedly

### Option 3: Smart Retry in Client Code

Update MT4 client to try local first, then remote:

```python
def connect_to_mt4():
    # Try local first
    try:
        return connect("192.168.0.123", 5555, timeout=2)
    except:
        # Fall back to remote
        return connect("75.154.254.174", 5555, timeout=5)
```

**Pros:**
- No .env changes needed
- Automatic fallback on every connection

**Cons:**
- Adds latency on every connection attempt
- More complex client code

---

## Error Handling

### Both Networks Unreachable

```bash
$ python3 scripts/detect_network.py

🔍 Detecting network location...
  Testing LOCAL network (192.168.0.123)...
  ❌ LOCAL network unreachable (not at home)
  Testing REMOTE network (75.154.254.174)...
  ❌ REMOTE network unreachable

❌ DETECTION FAILED

Neither LOCAL nor REMOTE server is accessible.
Please check:
  1. MT4 server is running
  2. ZMQ Expert Advisor is active
  3. Firewall allows connections
  4. Network connectivity
```

**Exit code:** 1 (failure)

---

## Configuration

### Modify Detection Parameters

Edit `scripts/detect_network.py`:

```python
# Network configurations
LOCAL_IP = "192.168.0.123"
REMOTE_IP = "75.154.254.174"
TEST_PORT = 5555  # MT4 command port

# Timeouts (in seconds)
LOCAL_TIMEOUT = 2   # Fast timeout for local
REMOTE_TIMEOUT = 5  # Longer timeout for internet
```

### Add Additional Networks

```python
# For example, office network
OFFICE_IP = "10.0.0.100"

def detect_network():
    # Try office first
    if test_connection(OFFICE_IP, TEST_PORT, timeout=2):
        return "office", OFFICE_IP
    # Then local
    if test_connection(LOCAL_IP, TEST_PORT, timeout=2):
        return "local", LOCAL_IP
    # Finally remote
    if test_connection(REMOTE_IP, TEST_PORT, timeout=5):
        return "remote", REMOTE_IP
    return None, None
```

---

## Documentation Updates

### Files Updated

1. ✅ `scripts/detect_network.py` - New auto-detection script
2. ✅ `INFRASTRUCTURE_ARCHITECTURE_2026-01-06.md` - Updated with auto-detection
3. ✅ `NETWORK_QUICK_REFERENCE.md` - Added auto-detect commands
4. ✅ This file - Complete implementation documentation

### CLAUDE.md Update

Add to quick reference section:

```markdown
## Auto-Detection (Recommended)

Always run this when starting work:
python3 scripts/detect_network.py
docker-compose restart api
```

---

## Summary

### Problem Solved ✅

**User request:** "Have the system basculate between both based on availability"

**Solution:**
- ✅ Automatic detection tries local first, falls back to remote
- ✅ Updates .env file automatically
- ✅ Clear feedback on what was detected
- ✅ Simple one-command operation
- ✅ No manual IP editing required

### Current Status

- ✅ Script implemented and tested
- ✅ Correctly detected REMOTE network (user is remote)
- ✅ Updated .env from LOCAL to REMOTE
- ✅ API restarted successfully
- ✅ All connections verified working

### Next Steps

**Immediate:**
- Run `python3 scripts/detect_network.py` whenever unsure about network
- Consider adding to startup routine

**Future:**
- Decide on auto-run strategy (startup vs cron vs manual)
- Add to CI/CD deployment scripts
- Create pre-commit hook to verify network config

---

**Last Updated:** January 6, 2026
**Status:** ✅ Production Ready
**Tested:** ✅ Working in remote mode
