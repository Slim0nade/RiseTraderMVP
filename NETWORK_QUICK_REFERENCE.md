# Network Quick Reference Card

## 🔴 CRITICAL: Unified Server Architecture

**Both Ollama + MT4 on SAME server:**
- Local (at home): `192.168.0.123`
- Remote (anywhere): `75.154.254.174`

---

## Quick Switch Commands

### At Home (Use Local)
```bash
python3 scripts/switch_network.py local
docker-compose restart api
```

### Anywhere Else (Use Remote)
```bash
python3 scripts/switch_network.py remote
docker-compose restart api
```

### Check Current Config
```bash
python3 scripts/switch_network.py status
```

### Test Connections
```bash
python3 scripts/switch_network.py test
```

---

## Port Reference

| Service | Port | Purpose |
|---------|------|---------|
| Ollama | 11434 | LLM API |
| MT4 REP | 5555 | Commands |
| MT4 PUB | 5556 | Market data |

---

## Access URLs

### Local (192.168.0.123)
```bash
# Ollama
curl http://192.168.0.123:11434/api/tags

# MT4
telnet 192.168.0.123 5555
```

### Remote (75.154.254.174)
```bash
# Ollama
curl http://75.154.254.174:11434/api/tags

# MT4
telnet 75.154.254.174 5555
```

---

## ⚠️ Common Mistakes

### ❌ Mixing IPs (WRONG)
```bash
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://75.154.254.174:11434
```

### ✅ Matching IPs (CORRECT)
```bash
# Both local
MT4_HOST=192.168.0.123
OLLAMA_BASE_URL=http://192.168.0.123:11434

# OR both remote
MT4_HOST=75.154.254.174
OLLAMA_BASE_URL=http://75.154.254.174:11434
```

---

## Performance Comparison

| Metric | Local | Remote |
|--------|-------|--------|
| MT4 Latency | 1-5ms | 20-100ms |
| LLM Latency | 5-10s | 60-180s |
| Bandwidth | 1 Gbps | Your internet |
| Reliability | Very high | Internet-dependent |

**Recommendation:** Use LOCAL when possible (10-20× faster LLM)

---

## Available Models

- qwen3:14b
- deepseek-r1:14b
- mistral:7b-instruct
- llama3.1:8b

---

**Last Updated:** January 6, 2026
**See Also:**
- `INFRASTRUCTURE_ARCHITECTURE_2026-01-06.md` (detailed)
- `NETWORK_SWITCHING_GUIDE.md` (complete guide)
