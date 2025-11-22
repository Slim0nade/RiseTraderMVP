# MT4 Integration Setup Guide

This directory contains the MetaTrader 4 Expert Advisor for RiseTrader integration.

## 📁 Directory Structure

```
mt4/
├── README.md                              # This file
├── experts/
│   └── RiseTraderMT4Server.mq4           # Main EA for MT4 integration
└── libraries/
    └── (ZMQ library files go here)
```

---

## 🚀 Quick Start

### Option 1: **Python Mock EA** (For Development/Testing)

✅ **No MT4 required** - Use this for:
- Unit testing
- Integration testing
- CI/CD pipelines
- Development without MT4 access

```bash
# Start mock EA
python tests/integration/mock_mt4_ea.py

# Or with custom settings
python tests/integration/mock_mt4_ea.py --rep-port 5555 --pub-port 5556 --magic 100001
```

**Features of Mock EA:**
- ✅ Implements full ZMQ protocol
- ✅ Simulates market data streaming
- ✅ Simulates order execution
- ✅ Simulates P&L updates
- ✅ No encryption required (simplifies testing)
- ✅ Runs in background for automated tests

---

### Option 2: **Real MT4 EA** (For Production/E2E Testing)

⚠️ **Requires MT4** - Use this for:
- End-to-end testing with real MT4
- Production deployment
- Live/demo account trading

---

## 📦 Prerequisites for Real MT4 EA

### 1. Install MetaTrader 4

Download from your broker or:
- https://www.metatrader4.com/en/download

### 2. Install ZMQ Library for MQL4

The EA requires the **mql-zmq** library:

```bash
# Clone the library
git clone https://github.com/dingmaotu/mql-zmq.git

# Copy files to MT4
# On Windows:
copy mql-zmq\MQL4\Include\Zmq MT4_DATA_FOLDER\MQL4\Include\Zmq
copy mql-zmq\MQL4\Libraries\*.ex4 MT4_DATA_FOLDER\MQL4\Libraries\

# On Linux/Wine:
cp -r mql-zmq/MQL4/Include/Zmq ~/.wine/drive_c/Program\ Files\ \(x86\)/MetaTrader\ 4/MQL4/Include/
cp mql-zmq/MQL4/Libraries/*.ex4 ~/.wine/drive_c/Program\ Files\ \(x86\)/MetaTrader\ 4/MQL4/Libraries/
```

**MT4 Data Folder locations:**
- **Windows**: `C:\Users\[Username]\AppData\Roaming\MetaQuotes\Terminal\[Instance_ID]\`
- **macOS (Wine)**: `~/.wine/drive_c/Program Files (x86)/MetaTrader 4/`
- Or in MT4: `File → Open Data Folder`

### 3. Generate Encryption Keys

```bash
# Generate CurveZMQ keys
python scripts/generate_zmq_keys.py

# Copy output keys:
# - Client keys → .env file
# - Server keys → MT4 EA parameters (next step)
```

---

## ⚙️ Setup Instructions for Real MT4 EA

### Step 1: Copy EA to MT4

```bash
# Copy the EA file
# Windows:
copy mt4\experts\RiseTraderMT4Server.mq4 MT4_DATA_FOLDER\MQL4\Experts\

# macOS/Linux:
cp mt4/experts/RiseTraderMT4Server.mq4 ~/.wine/drive_c/.../MetaTrader\ 4/MQL4/Experts/
```

### Step 2: Compile in MetaEditor

1. Open **MetaEditor** in MT4 (`Tools → MetaQuotes Language Editor`)
2. Open `RiseTraderMT4Server.mq4`
3. Click **Compile** (F7)
4. Check for errors in the **Toolbox** tab
5. Fix any issues (usually missing ZMQ library)

### Step 3: Configure EA Parameters

1. In MT4, open **Navigator** panel (`Ctrl+N`)
2. Expand `Expert Advisors`
3. Find `RiseTraderMT4Server`
4. **Right-click** → `Properties`
5. Configure parameters:

```
ServerSecretKey  = [YOUR_SERVER_SECRET_KEY_FROM_KEYGEN]  (40 chars)
ServerPublicKey  = [YOUR_SERVER_PUBLIC_KEY_FROM_KEYGEN]  (40 chars)
ClientPublicKey  = [YOUR_CLIENT_PUBLIC_KEY_FROM_KEYGEN]  (40 chars)
REP_PORT         = 5555
PUB_PORT         = 5556
MagicNumber      = 100001
TradingSymbol    = CrudeOIL
EnableEncryption = true
EnableLogging    = true
```

### Step 4: Attach EA to Chart

1. Open a chart for your symbol (e.g., CrudeOIL)
2. **Drag** `RiseTraderMT4Server` from Navigator onto the chart
3. In the popup, configure the parameters (as above)
4. Check `Allow live trading` ✅
5. Check `Allow DLL imports` ✅ (required for ZMQ)
6. Click **OK**

### Step 5: Verify Connection

You should see in the **Experts** tab:
```
RiseTrader MT4 Server EA initializing...
Magic Number: 100001
REP Port: 5555
PUB Port: 5556
Symbol: CrudeOIL
Encryption: ENABLED
Encryption keys validated
REP socket bound to tcp://*:5555
PUB socket bound to tcp://*:5556
RiseTrader MT4 Server EA initialized successfully
```

---

## 🧪 Testing the Connection

### Test with Mock EA

```bash
# Terminal 1: Start mock EA
python tests/integration/mock_mt4_ea.py

# Terminal 2: Test connection
python -c "
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect('tcp://localhost:5555')

command = json.dumps({'command': 'test_connection', 'correlation_id': '12345'})
socket.send_string(command)

response = socket.recv_string()
print('Response:', response)
"
```

### Test with Real MT4 EA

```bash
# Test connection to real MT4
python -c "
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect('tcp://75.154.254.186:5555')  # Your MT4 server IP

# If encryption is enabled, configure keys:
# socket.curve_secretkey = b'YOUR_CLIENT_SECRET_KEY'
# socket.curve_publickey = b'YOUR_CLIENT_PUBLIC_KEY'
# socket.curve_serverkey = b'YOUR_SERVER_PUBLIC_KEY'

command = json.dumps({'command': 'test_connection'})
socket.send_string(command)

response = socket.recv_string()
print('Response:', response)
"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Connection OK",
  "magic_number": 100001,
  "symbol": "CrudeOIL",
  "server_time": "2025-11-21 14:30:00"
}
```

---

## 📡 ZMQ Protocol Reference

### Commands (REQ/REP Socket - Port 5555)

#### 1. Test Connection
```json
{
  "command": "test_connection",
  "correlation_id": "uuid-here"
}
```

#### 2. Create Market Order
```json
{
  "command": "create_instant_order",
  "symbol": "CrudeOIL",
  "direction": "BUY",
  "volume": 0.1,
  "magic_number": 100001,
  "stop_loss": 75.00,
  "take_profit": 80.00,
  "correlation_id": "uuid-here"
}
```

#### 3. Get Account Info
```json
{
  "command": "get_account_info",
  "magic_number": 100001,
  "correlation_id": "uuid-here"
}
```

#### 4. Get Open Positions
```json
{
  "command": "get_open_positions",
  "magic_number": 100001,
  "correlation_id": "uuid-here"
}
```

#### 5. Close Position
```json
{
  "command": "close_position",
  "ticket_number": 12345,
  "magic_number": 100001,
  "correlation_id": "uuid-here"
}
```

### Events (PUB/SUB Socket - Port 5556)

#### 1. Market Tick
```json
{
  "event_type": "market_tick",
  "version": "1.0.0",
  "timestamp": "2025-11-21T14:30:00Z",
  "data": {
    "symbol": "CrudeOIL",
    "bid": 75.50,
    "ask": 75.55
  }
}
```

#### 2. Order Confirmed
```json
{
  "event_type": "order_confirmed",
  "version": "1.0.0",
  "timestamp": "2025-11-21T14:30:00Z",
  "data": {
    "ticket_number": 12345,
    "magic_number": 100001,
    "symbol": "CrudeOIL",
    "direction": "BUY",
    "volume": 0.1,
    "execution_price": 75.55,
    "execution_time": "2025-11-21T14:30:00Z"
  }
}
```

#### 3. Position Updated
```json
{
  "event_type": "position_updated",
  "version": "1.0.0",
  "timestamp": "2025-11-21T14:30:00Z",
  "data": {
    "ticket_number": 12345,
    "magic_number": 100001,
    "symbol": "CrudeOIL",
    "direction": "BUY",
    "volume": 0.1,
    "open_price": 75.55,
    "current_price": 75.60,
    "unrealized_pnl": 50.00,
    "stop_loss": 75.00,
    "take_profit": 80.00
  }
}
```

#### 4. Position Closed
```json
{
  "event_type": "position_closed",
  "version": "1.0.0",
  "timestamp": "2025-11-21T14:30:00Z",
  "data": {
    "ticket_number": 12345,
    "magic_number": 100001
  }
}
```

#### 5. Connection Status
```json
{
  "event_type": "connection_status_changed",
  "version": "1.0.0",
  "timestamp": "2025-11-21T14:30:00Z",
  "data": {
    "magic_number": 100001,
    "status": "ACTIVE",
    "error_message": ""
  }
}
```

---

## 🔒 Security Checklist

Before production deployment:

- [ ] CurveZMQ encryption enabled (`EnableEncryption = true`)
- [ ] Keys generated with `scripts/generate_zmq_keys.py`
- [ ] Keys stored securely (not in code)
- [ ] Client keys in `.env` file (gitignored)
- [ ] Server keys configured in MT4 EA parameters only
- [ ] Firewall rules configured for ports 5555-5556
- [ ] VPN or secure network for MT4 server
- [ ] Regular key rotation (every 90 days)
- [ ] `ENABLE_LIVE_TRADING=false` in .env until validated

---

## 🐛 Troubleshooting

### EA Not Compiling

**Error**: `'Context' - undeclared identifier`

**Fix**: Install mql-zmq library (see Prerequisites above)

---

### EA Not Sending/Receiving

**Error**: Silent failures, no logs

**Fix**:
1. Check `Allow DLL imports` is enabled
2. Check `Allow live trading` is enabled
3. Verify ports are not blocked by firewall
4. Check MT4 **Experts** tab for error messages

---

### Connection Refused

**Error**: `Connection refused on tcp://localhost:5555`

**Fix**:
1. Verify EA is running (check chart for smiley face icon)
2. Verify correct ports in EA parameters
3. Check firewall allows connections
4. Test with `netstat -an | grep 5555` to see if port is listening

---

### Encryption Errors

**Error**: `Invalid server key` or authentication failures

**Fix**:
1. Regenerate keys: `python scripts/generate_zmq_keys.py`
2. Verify keys are exactly 40 characters (Z85-encoded)
3. Check no trailing spaces/newlines in keys
4. Verify keys match between client (Python) and server (MT4)
5. For testing, temporarily disable encryption

---

## 📚 Additional Resources

- **ZMQ Guide**: https://zeromq.org/get-started/
- **MQL4 Documentation**: https://docs.mql4.com/
- **mql-zmq Library**: https://github.com/dingmaotu/mql-zmq
- **CurveZMQ Spec**: https://rfc.zeromq.org/spec:26/CURVEZMQ/
- **RiseTrader Docs**: `../docs/`

---

## 🎯 Next Steps

After setting up the MT4 EA:

1. **Test with mock EA** first (no MT4 required)
2. **Verify protocol** with simple commands
3. **Test with real MT4** EA in demo account
4. **Run integration tests** (`pytest tests/integration/`)
5. **Enable encryption** for production
6. **Deploy to production** only after thorough testing

---

**Happy Trading! 🚀**
