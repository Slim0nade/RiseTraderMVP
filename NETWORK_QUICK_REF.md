# Network Switching - Quick Reference Card

## 🏠 AT HOME (Local Network)
```bash
python3 scripts/switch_network.py local
docker-compose restart api
```
**Connects to:** 192.168.0.123

---

## 🌐 AWAY FROM HOME (Internet)
```bash
python3 scripts/switch_network.py remote
docker-compose restart api
```
**Connects to:** 75.154.254.174

---

## 🔍 CHECK CURRENT LOCATION
```bash
python3 scripts/switch_network.py status
```

---

## 🧪 TEST CONNECTIONS
```bash
python3 scripts/switch_network.py test
```

---

## ⚙️ WHAT SWITCHES AUTOMATICALLY

✅ **MT4 Connection**
- Command endpoint (port 5555)
- Stream endpoint (port 5556)

✅ **Ollama Connection**
- Base URL for LLM inference
- Timeout settings (60s local, 120s remote)
- Retry counts (3 local, 5 remote)

---

## ⚠️ REMEMBER

**ALWAYS restart API after switching:**
```bash
docker-compose restart api
```

Otherwise services will use old configuration!

---

## 📋 NETWORK DETAILS

| Setting | LOCAL (Home) | REMOTE (Internet) |
|---------|--------------|-------------------|
| IP Address | 192.168.0.123 | 75.154.254.174 |
| MT4 Command | 192.168.0.123:5555 | 75.154.254.174:5555 |
| MT4 Stream | 192.168.0.123:5556 | 75.154.254.174:5556 |
| Ollama URL | http://192.168.0.123:11434 | http://75.154.254.174:11434 |
| Timeout | 60 seconds | 120 seconds |
| Max Retries | 3 | 5 |

---

## 🔧 TROUBLESHOOTING

**Can't connect after switching?**
```bash
# 1. Verify switch worked
python3 scripts/switch_network.py status

# 2. Restart ALL services
docker-compose down
docker-compose up -d

# 3. Test connections
python3 scripts/switch_network.py test
```

**Ollama not responding?**
```bash
# Test manually
curl http://75.154.254.174:11434/api/tags  # Remote
curl http://192.168.0.123:11434/api/tags   # Local
```

**MT4 not responding?**
- Check if MT4 is running
- Check if ZMQ_Server_EA is active
- Look for "ZMQ Server started" in MT4 logs

---

**Full Documentation:** `NETWORK_SWITCHING_GUIDE.md`
