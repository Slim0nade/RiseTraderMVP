# RiseTrader Infrastructure Architecture - 2026-01-06

## 🔴 CRITICAL: Unified Server Architecture

**IMPORTANT:** Both Ollama LLM server AND MT4 trading platform run on the **SAME physical server**.

This server has **TWO access methods** depending on your location:

---

## Server Access Methods

### **Local (Home Network) - 192.168.0.123**
Use when you're physically at home on the same network:
- Faster latency (LAN speeds)
- No internet routing
- More reliable connection

### **Remote (Internet) - 75.154.254.174**
Use when you're anywhere else (coffee shop, office, traveling):
- Accessible over public internet
- Higher latency (internet routing)
- Requires port forwarding/public access

---

## Services on Unified Server

```
┌─────────────────────────────────────────────────────────┐
│  Physical Server (Windows VPS)                          │
│  Local IP:  192.168.0.123                              │
│  Public IP: 75.154.254.174                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐    ┌──────────────────┐         │
│  │  Ollama Server   │    │  MetaTrader 4    │         │
│  │  Port: 11434     │    │  ZMQ Ports:      │         │
│  │                  │    │  - REP: 5555     │         │
│  │  Models:         │    │  - PUB: 5556     │         │
│  │  - qwen3:14b     │    │                  │         │
│  │  - deepseek-r1   │    │  Expert Advisor: │         │
│  │  - mistral:7b    │    │  ZMQ_Server_EA   │         │
│  │  - llama3.1:8b   │    │                  │         │
│  └──────────────────┘    └──────────────────┘         │
│                                                         │
└─────────────────────────────────────────────────────────┘
           ▲                           ▲
           │                           │
    ┌──────┴───────┐          ┌───────┴────────┐
    │              │          │                │
 LOCAL ACCESS  REMOTE ACCESS
192.168.0.123   75.154.254.174
```

---

## Client Configuration (Your Mac)

```
┌─────────────────────────────────────────────────────────┐
│  MacBook (Development Machine)                          │
│  Docker Containers:                                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────┐       │
│  │  risetrader-api (FastAPI)                   │       │
│  │  Port: 8003                                 │       │
│  │                                             │       │
│  │  Connects to REMOTE server:                │       │
│  │  - MT4: tcp://[IP]:5555 (REP)              │       │
│  │  - MT4: tcp://[IP]:5556 (PUB)              │       │
│  │  - Ollama: http://[IP]:11434/api           │       │
│  │                                             │       │
│  │  [IP] = 192.168.0.123 OR 75.154.254.174    │       │
│  │  (controlled by NETWORK_LOCATION env var)  │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  ┌─────────────────────────────────────────────┐       │
│  │  risetrader-postgres                        │       │
│  │  Port: 5433                                 │       │
│  │  13.5M candles stored locally               │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  ┌─────────────────────────────────────────────┐       │
│  │  risetrader-redis                           │       │
│  │  Port: 6379                                 │       │
│  │  Pub/sub for real-time events              │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Network Configuration

### Environment Variable: `NETWORK_LOCATION`

**Controls BOTH services simultaneously:**

```bash
# .env file
NETWORK_LOCATION=local    # or "remote"

# When NETWORK_LOCATION=local:
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://192.168.0.123:11434

# When NETWORK_LOCATION=remote:
MT4_HOST=75.154.254.174
OLLAMA_BASE_URL=http://75.154.254.174:11434
```

### ⚠️ CRITICAL: Always Update BOTH Services Together

**WRONG:**
```bash
# DON'T do this - creates mismatch!
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://75.154.254.174:11434  # ❌ Different IPs
```

**CORRECT:**
```bash
# Use the switch script - updates both automatically
python3 scripts/switch_network.py local

# OR manually set both to same IP:
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://192.168.0.123:11434  # ✅ Same server
```

---

## Port Mapping

### **Same Server, Different Ports:**

| Service | Protocol | Port | Purpose |
|---------|----------|------|---------|
| Ollama | HTTP | 11434 | LLM API endpoint |
| MT4 ZMQ REP | TCP | 5555 | Command channel (request/reply) |
| MT4 ZMQ PUB | TCP | 5556 | Stream channel (market data) |

**All accessible via:**
- Local: `192.168.0.123:[port]`
- Remote: `75.154.254.174:[port]`

---

## Network Switching Workflow

### Scenario 1: At Home → Going Remote

```bash
# 1. Check current status
python3 scripts/switch_network.py status
# Output: NETWORK_LOCATION: local

# 2. Switch to remote (before leaving home)
python3 scripts/switch_network.py remote

# 3. Restart services
docker-compose restart api

# 4. Verify connection
python3 scripts/switch_network.py test
```

### Scenario 2: Remote → Coming Home

```bash
# 1. Check current status
python3 scripts/switch_network.py status
# Output: NETWORK_LOCATION: remote

# 2. Switch to local (after arriving home)
python3 scripts/switch_network.py local

# 3. Restart services
docker-compose restart api

# 4. Verify connection
python3 scripts/switch_network.py test
```

---

## Performance Comparison

### Local Network (192.168.0.123)
- **MT4 Latency:** ~1-5ms
- **Ollama Latency:** ~5-10s per LLM call (GPU inference)
- **Bandwidth:** 1 Gbps LAN
- **Reliability:** Very high (no internet dependency)

### Remote Network (75.154.254.174)
- **MT4 Latency:** ~20-100ms (depends on your internet)
- **Ollama Latency:** ~60-180s per LLM call (network + inference)
- **Bandwidth:** Limited by your internet upload speed
- **Reliability:** Depends on internet stability

**Recommendation:** Use LOCAL when possible for 10-20× faster LLM calls.

---

## Connection Testing

### Test Ollama Connectivity

```bash
# Local
curl http://192.168.0.123:11434/api/tags

# Remote
curl http://75.154.254.174:11434/api/tags

# Should return JSON with list of models
```

### Test MT4 Connectivity

```bash
# Local command port
telnet 192.168.0.123 5555

# Remote command port
telnet 75.154.254.174 5555

# Should connect successfully
```

### Automated Test

```bash
python3 scripts/switch_network.py test
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Mixing IP Addresses
```bash
# WRONG - Don't mix local and remote IPs
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://75.154.254.174:11434
```

**Why Wrong:** They're on the same server. Use the same IP for both.

### ❌ Mistake 2: Forgetting to Restart API
```bash
# Changed .env but didn't restart
python3 scripts/switch_network.py local
# (API still using old config)
```

**Fix:** Always restart after switching:
```bash
docker-compose restart api
```

### ❌ Mistake 3: Using Wrong IP for Your Location
```bash
# At home but using remote IP
NETWORK_LOCATION=remote  # ❌ Slow, unnecessary internet routing

# Should be:
NETWORK_LOCATION=local   # ✅ Fast local connection
```

### ❌ Mistake 4: Hardcoding IPs in Code
```python
# WRONG - Don't hardcode IPs
ollama_url = "http://192.168.0.123:11434"  # ❌ Won't work remotely

# CORRECT - Use network manager
from src.config.network_config import get_ollama_base_url
ollama_url = get_ollama_base_url()  # ✅ Automatically correct
```

---

## Security Considerations

### Current Setup (Development)
- ✅ Services accessible on local network
- ✅ Services accessible over internet (port forwarding)
- ❌ No encryption on connections
- ❌ No authentication on services
- ⚠️ Public IP exposed to internet

### Production Recommendations

**1. VPN Access (Recommended)**
```
Instead of public IP, use VPN:
- Set up WireGuard or OpenVPN on server
- Connect via VPN from anywhere
- Use 192.168.0.123 (private IP) even when remote
- No port forwarding needed
```

**2. ZMQ Encryption**
```bash
# Enable CurveZMQ encryption for MT4
ZMQ_CLIENT_SECRET_KEY=<generated>
ZMQ_CLIENT_PUBLIC_KEY=<generated>
ZMQ_SERVER_PUBLIC_KEY=<generated>
```

**3. Ollama Authentication**
```bash
# Use reverse proxy with auth (nginx)
# Or restrict by IP whitelist
```

**4. Firewall Rules**
```bash
# Only allow your client IP
iptables -A INPUT -p tcp --dport 11434 -s YOUR_IP -j ACCEPT
iptables -A INPUT -p tcp --dport 5555 -s YOUR_IP -j ACCEPT
iptables -A INPUT -p tcp --dport 5556 -s YOUR_IP -j ACCEPT
```

---

## Disaster Recovery

### What if the server is down?

**MT4 is unavailable:**
- ❌ Cannot execute live trades
- ❌ Cannot stream market data
- ✅ Can still run backtests (using local database)
- ✅ Can still view historical data

**Ollama is unavailable:**
- ❌ Cannot use LLM agents for trading decisions
- ❌ Cannot run agent-based backtests
- ✅ Can still use synthetic strategies (MA crossover, RSI, etc.)
- ✅ Can still view dashboard and historical data

**Backup Plan:**
- Keep local Ollama instance ready (Docker container)
- Use synthetic strategies for backtesting
- Deploy to DigitalOcean for redundancy

---

## Future: DigitalOcean Deployment

When deploying to production on DigitalOcean:

```
Option A: Move Everything to Cloud
┌────────────────────────────────────┐
│  DigitalOcean Droplet              │
│  - FastAPI (API server)            │
│  - Ollama (with GPU droplet)       │
│  - PostgreSQL (managed DB)         │
│  - Redis (managed)                 │
└────────────────────────────────────┘
         │
         │ (Still connects to home server for MT4)
         ▼
┌────────────────────────────────────┐
│  Home Server (VPS)                 │
│  - MT4 with ZMQ                    │
│  (192.168.0.123 / 75.154.254.174)  │
└────────────────────────────────────┘

Option B: Keep MT4 + Ollama Local, API in Cloud
┌────────────────────────────────────┐
│  DigitalOcean Droplet              │
│  - FastAPI (API server)            │
│  - PostgreSQL (managed DB)         │
│  - Redis (managed)                 │
└────────────────────────────────────┘
         │
         │ (Connects to home server for both)
         ▼
┌────────────────────────────────────┐
│  Home Server (VPS)                 │
│  - MT4 with ZMQ                    │
│  - Ollama (local GPU)              │
│  (192.168.0.123 / 75.154.254.174)  │
└────────────────────────────────────┘
```

---

## Quick Reference

### Current Setup Summary
| Component | Location | Access |
|-----------|----------|--------|
| Ollama | Home server | 192.168.0.123:11434 OR 75.154.254.174:11434 |
| MT4 | Home server | 192.168.0.123:5555/5556 OR 75.154.254.174:5555/5556 |
| FastAPI | MacBook (Docker) | localhost:8003 |
| PostgreSQL | MacBook (Docker) | localhost:5433 |
| Redis | MacBook (Docker) | localhost:6379 |
| Dashboard | MacBook (local) | localhost:3000 |

### Essential Commands
```bash
# Check current network
python3 scripts/switch_network.py status

# Switch to local (at home)
python3 scripts/switch_network.py local && docker-compose restart api

# Switch to remote (anywhere else)
python3 scripts/switch_network.py remote && docker-compose restart api

# Test connections
python3 scripts/switch_network.py test
```

---

**Last Updated:** January 6, 2026
**Documentation Version:** 2.0
**Critical Change:** Clarified unified server architecture (Ollama + MT4 on same server)
