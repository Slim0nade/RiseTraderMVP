# Network Location Switching Guide

## Overview

RiseTrader now supports automatic switching between **LOCAL** (home network) and **REMOTE** (internet) connections for both **MT4** and **Ollama** services.

This allows you to:
- ✅ Work from home using fast local connections (192.168.0.123)
- ✅ Work remotely using internet connections (75.154.254.174)
- ✅ Switch between networks with a single command
- ✅ Maintain consistent configuration across the system

---

## Network Endpoints

### LOCAL (Home Network)
- **IP Address**: `192.168.0.123`
- **MT4 Command Port**: `5555`
- **MT4 Stream Port**: `5556`
- **Ollama Base URL**: `http://192.168.0.123:11434`
- **Timeout**: 60 seconds
- **Max Retries**: 3

### REMOTE (Internet)
- **IP Address**: `75.154.254.174`
- **MT4 Command Port**: `5555`
- **MT4 Stream Port**: `5556`
- **Ollama Base URL**: `http://75.154.254.174:11434`
- **Timeout**: 120 seconds (longer for internet latency)
- **Max Retries**: 5 (more retries for reliability)

---

## Quick Start

### 1. Check Current Network Location

```bash
python3 scripts/switch_network.py status
```

**Output:**
```
============================================================
🌐 CURRENT NETWORK LOCATION: REMOTE
============================================================

📡 MT4 Connection:
   Host:            75.154.254.174
   Command Port:    5555
   Stream Port:     5556
   Command Endpoint: tcp://75.154.254.174:5555
   Stream Endpoint:  tcp://75.154.254.174:5556

🤖 Ollama Connection:
   Base URL:        http://75.154.254.174:11434
   API URL:         http://75.154.254.174:11434/api
   Timeout:         120s
   Max Retries:     5
============================================================
```

### 2. Switch to LOCAL (Home)

```bash
python3 scripts/switch_network.py local
```

**Output:**
```
🔄 Switching to LOCAL network (192.168.0.123)...
✅ Updated .env file with LOCAL configuration

✅ Network location switched to LOCAL
   MT4:    192.168.0.123
   Ollama: http://192.168.0.123:11434

⚠️  Restart services for changes to take effect:
   docker-compose restart api
```

### 3. Switch to REMOTE (Internet)

```bash
python3 scripts/switch_network.py remote
```

**Output:**
```
🔄 Switching to REMOTE network (75.154.254.174)...
✅ Updated .env file with REMOTE configuration

✅ Network location switched to REMOTE
   MT4:    75.154.254.174
   Ollama: http://75.154.254.174:11434

⚠️  Restart services for changes to take effect:
   docker-compose restart api
```

### 4. Test Connections

```bash
python3 scripts/switch_network.py test
```

This will:
- Show current network configuration
- Test Ollama connection (list available models)
- Test MT4 connection (ping test)

---

## How It Works

### 1. **Network Location Manager** (`src/config/network_config.py`)

The `NetworkLocationManager` class provides:
- Centralized network configuration
- Automatic environment variable reading
- Network switching capabilities
- Helper functions for getting endpoints

```python
from src.config.network_config import get_network_manager, NetworkLocation

# Get current configuration
manager = get_network_manager()

# Get MT4 config
mt4_config = manager.get_mt4_config()
print(f"MT4 Host: {mt4_config.host}")
print(f"Command: {mt4_config.command_endpoint}")

# Get Ollama config
ollama_config = manager.get_ollama_config()
print(f"Ollama: {ollama_config.base_url}")

# Switch to local
manager.set_location(NetworkLocation.LOCAL)
```

### 2. **Environment Variable** (`.env`)

The `NETWORK_LOCATION` variable controls the network:

```bash
# Set to "local" for home network
NETWORK_LOCATION=local

# Set to "remote" for internet
NETWORK_LOCATION=remote
```

When you switch networks, the script automatically updates:
- `NETWORK_LOCATION`
- `MT4_HOST`
- `OLLAMA_BASE_URL`

### 3. **Automatic Configuration**

Services that use the network manager will automatically use the correct endpoints:
- MT4 client connections
- Ollama API calls
- Agent configurations
- Backtesting pipelines

---

## Using in Code

### Python Code Example

```python
from src.config.network_config import (
    get_network_manager,
    get_mt4_host,
    get_ollama_base_url,
    NetworkLocation,
)

# Simple helpers
mt4_host = get_mt4_host()
ollama_url = get_ollama_base_url()

# Full manager
manager = get_network_manager()

# Check location
if manager.is_local():
    print("Using home network")
else:
    print("Using internet connection")

# Get detailed config
mt4 = manager.get_mt4_config()
print(f"Connecting to MT4 at {mt4.command_endpoint}")

ollama = manager.get_ollama_config()
print(f"Ollama API: {ollama.api_url}")
```

### Agent Configuration Example

```python
from src.config.network_config import get_ollama_base_url

# Get current Ollama URL
ollama_url = get_ollama_base_url()

# Configure your agent
agent_config = {
    "model": "qwen3:14b",
    "base_url": ollama_url,  # Automatically uses correct endpoint
    "timeout": 120,
}
```

---

## Workflow Examples

### Scenario 1: Working from Home

```bash
# 1. Switch to local network
python3 scripts/switch_network.py local

# 2. Restart services
docker-compose restart api

# 3. Verify connection
python3 scripts/switch_network.py test

# 4. Run your backtest
python3 scripts/test_agent_backtest.py
```

### Scenario 2: Working Remotely

```bash
# 1. Switch to remote network
python3 scripts/switch_network.py remote

# 2. Restart services
docker-compose restart api

# 3. Verify connection
python3 scripts/switch_network.py test

# 4. Access dashboard from anywhere
# http://localhost:3003
```

### Scenario 3: Switching Mid-Session

```bash
# You were working at home, now going to a coffee shop

# 1. Stop current work
# Ctrl+C on running processes

# 2. Switch network
python3 scripts/switch_network.py remote

# 3. Restart services
docker-compose restart api

# 4. Resume work
# Everything now uses internet endpoints
```

---

## API Restart Required

**⚠️ IMPORTANT**: After switching networks, you **MUST** restart the API service:

```bash
docker-compose restart api
```

This ensures:
- New MT4 host is loaded
- New Ollama URL is active
- Connection pools are refreshed
- All agents use correct endpoints

---

## Troubleshooting

### Issue: "Cannot connect to Ollama"

**Check 1**: Verify Ollama is running
```bash
# Local
curl http://192.168.0.123:11434/api/tags

# Remote
curl http://75.154.254.174:11434/api/tags
```

**Check 2**: Verify network location
```bash
python3 scripts/switch_network.py status
```

**Fix**: Switch to correct network
```bash
python3 scripts/switch_network.py local  # or remote
docker-compose restart api
```

### Issue: "Cannot connect to MT4"

**Check 1**: Verify MT4 EA is running
- Open MetaTrader 4
- Check if "ZMQ_Server_EA" is active on chart
- Look for "ZMQ Server started" in logs

**Check 2**: Verify ports are accessible
```bash
# Test command port
telnet 75.154.254.174 5555  # or 192.168.0.123

# Test stream port
telnet 75.154.254.174 5556  # or 192.168.0.123
```

**Fix**: Restart MT4 EA or switch network
```bash
python3 scripts/switch_network.py [local|remote]
```

### Issue: "Services using old configuration"

**Cause**: Services not restarted after switch

**Fix**: Restart all services
```bash
docker-compose down
docker-compose up -d
```

---

## Security Considerations

### Current Setup (Development)
- ✅ MT4 accessible over internet (75.154.254.174)
- ✅ Ollama accessible over internet
- ❌ No encryption on MT4 ZMQ connection
- ❌ No authentication on Ollama

### Production Recommendations

1. **Enable ZMQ Encryption** (MT4)
   ```bash
   # Generate keys
   python3 scripts/generate_zmq_keys.py

   # Update .env
   ZMQ_CLIENT_SECRET_KEY=your-key
   ZMQ_CLIENT_PUBLIC_KEY=your-key
   ZMQ_SERVER_PUBLIC_KEY=your-key
   ```

2. **Add Firewall Rules**
   - Restrict MT4 ports (5555, 5556) to specific IPs
   - Restrict Ollama port (11434) to specific IPs
   - Use VPN for remote access

3. **Use HTTPS for Ollama** (Optional)
   - Set up nginx reverse proxy with SSL
   - Configure: `https://75.154.254.174:11434`

4. **API Key Authentication**
   - Enable API keys in .env
   - Use API_KEY header for all requests

---

## Configuration Files

### Modified Files

1. **`.env`** - Added NETWORK_LOCATION variable
2. **`src/config/network_config.py`** - Network manager (NEW)
3. **`scripts/switch_network.py`** - CLI switcher (NEW)

### Network Configuration Presets

Located in `src/config/network_config.py`:

```python
CONFIGS = {
    NetworkLocation.LOCAL: NetworkConfig(
        mt4=MT4Endpoints(host="192.168.0.123", ...),
        ollama=OllamaEndpoints(base_url="http://192.168.0.123:11434", ...),
    ),
    NetworkLocation.REMOTE: NetworkConfig(
        mt4=MT4Endpoints(host="75.154.254.174", ...),
        ollama=OllamaEndpoints(base_url="http://75.154.254.174:11434", ...),
    ),
}
```

To add a new location, modify this dictionary.

---

## Advanced Usage

### Programmatic Switching

```python
from src.config.network_config import set_network_location, NetworkLocation

# Switch to local
set_network_location(NetworkLocation.LOCAL)

# Switch to remote
set_network_location(NetworkLocation.REMOTE)
```

### Custom Endpoints (Override)

```python
from src.config.network_config import NetworkLocationManager, MT4Endpoints

# Create custom manager
manager = NetworkLocationManager()

# Override MT4 host temporarily
manager.CONFIGS[NetworkLocation.LOCAL].mt4.host = "192.168.0.100"
```

### Environment Variable Override

```bash
# Temporary override (doesn't modify .env)
NETWORK_LOCATION=local python3 scripts/test_agent_backtest.py
```

---

## Summary

✅ **Simple**: One command to switch networks
✅ **Automatic**: Both MT4 and Ollama switch together
✅ **Consistent**: All services use the same configuration
✅ **Flexible**: Easy to extend with new locations
✅ **Safe**: Default to REMOTE for safety

**Quick Commands:**
```bash
# Check current network
python3 scripts/switch_network.py status

# Switch to home network
python3 scripts/switch_network.py local
docker-compose restart api

# Switch to internet
python3 scripts/switch_network.py remote
docker-compose restart api

# Test connections
python3 scripts/switch_network.py test
```

---

**Last Updated**: December 19, 2025
