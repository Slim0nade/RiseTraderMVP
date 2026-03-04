//+------------------------------------------------------------------+
//|                                      ExpertsRiseTraderServer.mq4 |
//|                                   Copyright 2025, Tuniverse Ltd. |
//|                                       https://www.tuniverses.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2025, Tuniverse Ltd."
#property link      "https://www.tuniverses.com"
#property version   "1.01"
#property strict

// Import ZMQ library (requires mql-zmq library installation)
// Download from: https://github.com/dingmaotu/mql-zmq
#include <ZMQ/Zmq.mqh>

// Define a unique magic number for your EA
#define MAGIC_NUMBER 123456

// Maximum number of symbols we support streaming simultaneously
#define MAX_SYMBOLS 16

//+------------------------------------------------------------------+
//| Input parameters                                                  |
//+------------------------------------------------------------------+
extern string SymbolList = "CrudeOIL,USA500,BRENT_OIL,CORN,WHEAT,GBPJPY.,#TSLA,#MICROSOFT,GASOLINE,GOLD.";

//+------------------------------------------------------------------+
//| Global variables                                                  |
//+------------------------------------------------------------------+
Context context("helloworld");
Socket repSocket(context, ZMQ_REP);   // REQ/REP socket for commands (port 5555)
Socket pubSocket(context, ZMQ_PUB);   // PUB socket for streaming data  (port 5556)

// Multi-symbol state — populated in OnInit() by parsing SymbolList
string   g_symbols[];          // Active (broker-validated) symbol names
datetime g_lastUpdateTime[];   // Last M1 bar time seen per symbol (for new-bar detection)
datetime g_lastSendTime[];     // Last time we sent ANY update for this symbol (for heartbeat)
int      g_symbolCount = 0;    // Number of active symbols

ENUM_TIMEFRAMES g_timeframe = PERIOD_M1;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // Set timer for every 1 second to handle ZMQ requests frequently
    EventSetTimer(1);

    // Attempt to bind REP socket
    if(!repSocket.bind("tcp://*:5555"))
    {
        Print("Error: Unable to bind REP socket to tcp://*:5555");
        return(INIT_FAILED);
    }

    // Attempt to bind PUB socket
    if(!pubSocket.bind("tcp://*:5556"))
    {
        Print("Error: Unable to bind PUB socket to tcp://*:5556");
        repSocket.unbind("tcp://*:5555");
        return(INIT_FAILED);
    }

    // Parse SymbolList into g_symbols[], skipping symbols the broker does not carry
    string parts[];
    int count = StringSplit(SymbolList, ',', parts);
    if(count <= 0)
    {
        Print("Error: SymbolList is empty or could not be parsed.");
        repSocket.unbind("tcp://*:5555");
        pubSocket.unbind("tcp://*:5556");
        return(INIT_FAILED);
    }

    // Pre-size arrays to maximum
    ArrayResize(g_symbols,        MAX_SYMBOLS);
    ArrayResize(g_lastUpdateTime, MAX_SYMBOLS);
    ArrayResize(g_lastSendTime,   MAX_SYMBOLS);

    g_symbolCount = 0;
    for(int i = 0; i < count; i++)
    {
        string sym = StringTrimLeft(StringTrimRight(parts[i]));
        if(StringLen(sym) == 0)
            continue;

        // Validate: try to select (load) the symbol from the broker feed
        if(!SymbolSelect(sym, true))
        {
            Print("Warning: Symbol '", sym, "' not found on broker — skipping.");
            continue;
        }

        if(g_symbolCount >= MAX_SYMBOLS)
        {
            Print("Warning: MAX_SYMBOLS (", MAX_SYMBOLS, ") reached — ignoring remaining symbols.");
            break;
        }

        g_symbols[g_symbolCount]        = sym;
        g_lastUpdateTime[g_symbolCount] = iTime(sym, g_timeframe, 0);
        g_lastSendTime[g_symbolCount]   = TimeCurrent();
        Print("Registered symbol [", g_symbolCount, "]: ", sym,
              "  last bar=", TimeToString(g_lastUpdateTime[g_symbolCount]));
        g_symbolCount++;
    }

    if(g_symbolCount == 0)
    {
        Print("Error: No valid symbols found in SymbolList='", SymbolList, "'");
        repSocket.unbind("tcp://*:5555");
        pubSocket.unbind("tcp://*:5556");
        return(INIT_FAILED);
    }

    Print("MT4 Multi-Symbol Server initialized. Streaming ", g_symbolCount, " symbol(s).");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();

    if(!repSocket.unbind("tcp://*:5555"))
        Print("Warning: Failed to unbind REP socket.");

    if(!pubSocket.unbind("tcp://*:5556"))
        Print("Warning: Failed to unbind PUB socket.");

    Print("MT4 Multi-Symbol Server deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//| OnTick() fires only for the chart's own symbol.  We detect new  |
//| bars for the chart symbol here; all other symbols are handled    |
//| in OnTimer() which runs every second.                            |
//+------------------------------------------------------------------+
void OnTick()
{
    string chartSym = Symbol();
    for(int i = 0; i < g_symbolCount; i++)
    {
        if(g_symbols[i] == chartSym)
        {
            datetime currentBarTime = iTime(chartSym, g_timeframe, 0);
            if(currentBarTime != g_lastUpdateTime[i])
            {
                sendRealTimeUpdate(i);
                g_lastUpdateTime[i] = currentBarTime;
                g_lastSendTime[i]   = TimeCurrent();
            }
            break;
        }
    }
}

//+------------------------------------------------------------------+
//| Timer function — runs every second                               |
//| Responsibilities:                                                |
//|  1. Handle incoming ZMQ command requests                         |
//|  2. Detect new M1 bars for ALL symbols (covers non-chart symbols)|
//|  3. Send 60-second fallback heartbeat per symbol                 |
//|  4. Optional 5-minute debug test message                         |
//+------------------------------------------------------------------+
void OnTimer()
{
    // 1. Handle ZMQ command requests
    handleZmqRequests();

    // 2. Check each symbol for a new M1 bar and send on change.
    //    Also covers the chart symbol (no double-send risk: OnTick()
    //    already updated g_lastUpdateTime[i] when it fired).
    for(int i = 0; i < g_symbolCount; i++)
    {
        datetime currentBarTime = iTime(g_symbols[i], g_timeframe, 0);
        if(currentBarTime == 0)
            continue; // Symbol has no data yet

        if(currentBarTime != g_lastUpdateTime[i])
        {
            sendRealTimeUpdate(i);
            g_lastUpdateTime[i] = currentBarTime;
            g_lastSendTime[i]   = TimeCurrent();
        }
        else
        {
            // 3. Fallback heartbeat: resend if >60 seconds since last SEND
            //    Uses g_lastSendTime (wall-clock) not g_lastUpdateTime (bar time)
            //    to avoid feedback loop on stale symbols.
            if(TimeCurrent() - g_lastSendTime[i] >= 60)
            {
                sendRealTimeUpdate(i);
                g_lastSendTime[i] = TimeCurrent();
            }
        }
    }

    // 4. Optional: 5-minute debug test message
    if(TimeMinute(TimeCurrent()) % 5 == 0 && TimeSeconds(TimeCurrent()) == 0)
    {
        sendTestMessage();
    }
}

//+------------------------------------------------------------------+
//| Handle ZeroMQ REP requests                                       |
//+------------------------------------------------------------------+
void handleZmqRequests()
{
    ZmqMsg request;
    while(repSocket.recv(request, ZMQ_DONTWAIT))
    {
        string requestString = request.getData();
        Print("Received request: ", requestString);

        string response = processRequest(requestString);

        ZmqMsg replyMsg(response);
        if(!repSocket.send(replyMsg))
            Print("Error: Failed to send reply for request: ", requestString);
        else
            Print("Reply sent: ", response);
    }
}

//+------------------------------------------------------------------+
//| Process incoming commands (REQ/REP channel)                      |
//+------------------------------------------------------------------+
string processRequest(string requestString)
{
    string command = extractValue(requestString, "command");
    string response;

    if(command == "test_connection")
    {
        response = createJsonResponse("OK", "Connection successful");
    }
    else if(command == "login")
    {
        response = createJsonResponse("OK", "Login successful");
    }
    else if(command == "loadPair")
    {
        string symbol = extractValue(requestString, "symbol");
        if(SymbolSelect(symbol, true))
            response = createJsonResponse("OK", StringFormat("Symbol %s loaded", symbol));
        else
            response = createJsonResponse("ERROR", StringFormat("Failed to load symbol %s", symbol));
    }
    else if(command == "iClose" || command == "iOpen" || command == "iHigh" ||
            command == "iLow"   || command == "iTime"  || command == "iVolume")
    {
        string symbol      = extractValue(requestString, "symbol");
        string timeframeStr = extractValue(requestString, "timeframe");
        string timeStr     = extractValue(requestString, "time");

        ENUM_TIMEFRAMES timeframe = stringToTimeframe(timeframeStr);
        datetime time = StringToTime(timeStr);

        int shift = iBarShift(symbol, timeframe, time, false);
        if(shift == -1)
        {
            response = createJsonResponse("ERROR", "Invalid time or symbol.");
        }
        else
        {
            double value = 0;
            if(command == "iClose")  value = iClose(symbol, timeframe, shift);
            else if(command == "iOpen")   value = iOpen(symbol, timeframe, shift);
            else if(command == "iHigh")   value = iHigh(symbol, timeframe, shift);
            else if(command == "iLow")    value = iLow(symbol, timeframe, shift);
            else if(command == "iTime")   value = (double)iTime(symbol, timeframe, shift);
            else if(command == "iVolume") value = (double)iVolume(symbol, timeframe, shift);
            response = createJsonResponse("OK", "", StringFormat("\"return\":%d", (long)value));
        }
    }
    else if(command == "close_position")
    {
        string ticketStr = extractValue(requestString, "ticket");
        int ticket = StringToInteger(ticketStr);

        if(OrderSelect(ticket, SELECT_BY_TICKET))
        {
            bool result = OrderClose(ticket, OrderLots(), OrderClosePrice(), 3);
            if(result)
                response = createJsonResponse("OK", StringFormat("Position %d closed successfully", ticket));
            else
                response = createJsonResponse("ERROR", StringFormat("Failed to close position %d. Error: %d", ticket, GetLastError()));
        }
        else
        {
            response = createJsonResponse("ERROR", StringFormat("Position %d not found", ticket));
        }
    }
    else if(command == "getOHLCV")
    {
        string symbol      = extractValue(requestString, "symbol");
        string timeframeStr = extractValue(requestString, "timeframe");
        string timeStr     = extractValue(requestString, "time");

        ENUM_TIMEFRAMES timeframe = stringToTimeframe(timeframeStr);
        datetime time = StringToTime(timeStr);

        string ohlcvData = getOHLCV(symbol, timeframe, time);
        if(StringLen(ohlcvData) == 0)
            response = createJsonResponse("ERROR", "Invalid time or symbol.");
        else
            response = createJsonResponse("OK", "", StringFormat("\"ohlcv\":{%s}", ohlcvData));
    }
    else if(command == "get_open_positions")
    {
        string positions = getOpenPositions();
        response = createJsonResponse("OK", "", StringFormat("\"positions\":%s", positions));
    }
    else if(command == "get_trade_history")
    {
        string startTimeStr = extractValue(requestString, "start_time");
        string endTimeStr   = extractValue(requestString, "end_time");
        string ticketStr    = extractValue(requestString, "ticket");

        int startTime = (startTimeStr != "") ? StringToInteger(startTimeStr) : 0;
        int endTime   = (endTimeStr   != "") ? StringToInteger(endTimeStr)   : 0;
        int ticket    = (ticketStr    != "") ? StringToInteger(ticketStr)    : 0;

        response = getTradeHistory(startTime, endTime, ticket);
    }
    else if(command == "get_symbols")
    {
        string symbols = getSymbols();
        response = createJsonResponse("OK", "", StringFormat("\"symbols\":%s", symbols));
    }
    else if(command == "get_symbol_info")
    {
        string symbol = extractValue(requestString, "symbol");
        if(symbol == "")
            response = createJsonResponse("ERROR", "Symbol parameter required");
        else
        {
            string info = getSymbolInfo(symbol);
            response = createJsonResponse("OK", "", StringFormat("\"symbol_info\":%s", info));
        }
    }
    else if(command == "get_all_symbols_info")
    {
        string allInfo = getAllSymbolsInfo();
        response = createJsonResponse("OK", "", StringFormat("\"symbols\":%s", allInfo));
    }
    else if(command == "create_instant_order")
    {
        string symbol      = extractValue(requestString, "symbol");
        string orderTypeStr = extractValue(requestString, "order_type");
        string volumeStr   = extractValue(requestString, "volume");
        string stopLossStr = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");

        int orderType;
        if(orderTypeStr == "BUY")       orderType = OP_BUY;
        else if(orderTypeStr == "SELL") orderType = OP_SELL;
        else
        {
            response = createJsonResponse("ERROR", "Invalid order type.");
            Print("Invalid order type received: ", orderTypeStr);
            return response;
        }

        double volume     = StringToDouble(volumeStr);
        double stopLoss   = StringToDouble(stopLossStr);
        double takeProfit = StringToDouble(takeProfitStr);

        int ticket = createInstantOrder(symbol, orderType, volume, stopLoss, takeProfit);
        if(ticket > 0)
            response = createJsonResponse("OK", StringFormat("Order created with ticket %d", ticket));
        else
            response = createJsonResponse("ERROR", StringFormat("Failed to create order. Error: %d", GetLastError()));
    }
    else if(command == "create_pending_order")
    {
        string symbol      = extractValue(requestString, "symbol");
        string orderTypeStr = extractValue(requestString, "order_type");
        string volumeStr   = extractValue(requestString, "volume");
        string priceStr    = extractValue(requestString, "price");
        string stopLossStr = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");

        int orderType;
        if(orderTypeStr == "BUY_LIMIT")       orderType = OP_BUYLIMIT;
        else if(orderTypeStr == "SELL_LIMIT")  orderType = OP_SELLLIMIT;
        else if(orderTypeStr == "BUY_STOP")    orderType = OP_BUYSTOP;
        else if(orderTypeStr == "SELL_STOP")   orderType = OP_SELLSTOP;
        else
        {
            response = createJsonResponse("ERROR", "Invalid pending order type.");
            Print("Invalid pending order type received: ", orderTypeStr);
            return response;
        }

        double volume     = StringToDouble(volumeStr);
        double price      = StringToDouble(priceStr);
        double stopLoss   = StringToDouble(stopLossStr);
        double takeProfit = StringToDouble(takeProfitStr);

        int ticket = createPendingOrder(symbol, orderType, volume, price, stopLoss, takeProfit);
        if(ticket > 0)
            response = createJsonResponse("OK", StringFormat("Pending order created with ticket %d", ticket));
        else
            response = createJsonResponse("ERROR", StringFormat("Failed to create pending order. Error: %d", GetLastError()));
    }
    else if(command == "get_account_info")
    {
        string accountInfo = getAccountInfo();
        response = createJsonResponse("OK", "", StringFormat("\"account_info\":{%s}", accountInfo));
    }
    else if(command == "get_pending_orders")
    {
        string pendingOrders = getPendingOrders();
        response = createJsonResponse("OK", "", StringFormat("\"orders\":%s", pendingOrders));
    }
    else if(command == "modify_position")
    {
        string ticketStr     = extractValue(requestString, "ticket");
        string stopLossStr   = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");

        int    ticket        = StringToInteger(ticketStr);
        double newStopLoss   = StringToDouble(stopLossStr);
        double newTakeProfit = StringToDouble(takeProfitStr);

        if(OrderSelect(ticket, SELECT_BY_TICKET))
        {
            int orderType = OrderType();
            if(orderType == OP_BUY || orderType == OP_SELL)
            {
                string symbol = OrderSymbol();
                int digits = (int)MarketInfo(symbol, MODE_DIGITS);

                double sl = (newStopLoss  > 0) ? NormalizeDouble(newStopLoss, digits)  : OrderStopLoss();
                double tp = (newTakeProfit > 0) ? NormalizeDouble(newTakeProfit, digits) : OrderTakeProfit();

                // Detect no-change scenario (Error 2 prevention)
                if(NormalizeDouble(sl - OrderStopLoss(), digits) == 0 &&
                   NormalizeDouble(tp - OrderTakeProfit(), digits) == 0)
                {
                    response = createJsonResponse("OK",
                        StringFormat("Position %d already has SL=%.5f TP=%.5f", ticket, sl, tp));
                }
                else
                {
                    bool result = OrderModify(ticket, OrderOpenPrice(), sl, tp, 0, clrNONE);
                    if(result)
                        response = createJsonResponse("OK",
                            StringFormat("Position %d modified: SL=%.5f, TP=%.5f", ticket, sl, tp));
                    else
                        response = createJsonResponse("ERROR",
                            StringFormat("Failed to modify position %d. Error: %d (SL=%.5f->%.5f, TP=%.5f->%.5f)",
                                ticket, GetLastError(), OrderStopLoss(), sl, OrderTakeProfit(), tp));
                }
            }
            else
            {
                response = createJsonResponse("ERROR",
                    StringFormat("Ticket %d is a pending order, not an open position.", ticket));
            }
        }
        else
        {
            response = createJsonResponse("ERROR", StringFormat("Position %d not found", ticket));
        }
    }
    else if(command == "delete_pending_order")
    {
        string ticketStr = extractValue(requestString, "ticket");
        int ticket = StringToInteger(ticketStr);

        if(OrderSelect(ticket, SELECT_BY_TICKET))
        {
            int orderType = OrderType();
            if(orderType >= OP_BUYLIMIT && orderType <= OP_SELLSTOP)
            {
                bool result = OrderDelete(ticket);
                if(result)
                    response = createJsonResponse("OK", StringFormat("Pending order %d deleted successfully", ticket));
                else
                    response = createJsonResponse("ERROR", StringFormat("Failed to delete pending order %d. Error: %d", ticket, GetLastError()));
            }
            else
            {
                response = createJsonResponse("ERROR", StringFormat("Order %d is not a pending order (type: %d)", ticket, orderType));
            }
        }
        else
        {
            response = createJsonResponse("ERROR", StringFormat("Pending order %d not found", ticket));
        }
    }
    else
    {
        response = createJsonResponse("ERROR", "Unknown command");
    }

    return response;
}

//+------------------------------------------------------------------+
//| Build a JSON response envelope                                   |
//+------------------------------------------------------------------+
string createJsonResponse(string status, string message, string additional = "")
{
    if(additional == "")
        return StringFormat("{\"status\":\"%s\",\"message\":\"%s\"}", status, message);
    else
        return StringFormat("{\"status\":\"%s\",\"message\":\"%s\",%s}", status, message, additional);
}

//+------------------------------------------------------------------+
//| Extract a string value from a flat JSON string                   |
//+------------------------------------------------------------------+
string extractValue(string jsonString, string key)
{
    int keyPos = StringFind(jsonString, "\"" + key + "\"");
    if(keyPos == -1) return "";
    int colonPos = StringFind(jsonString, ":", keyPos);
    if(colonPos == -1) return "";
    int valueStart = colonPos + 1;
    int valueEnd = StringFind(jsonString, ",", valueStart);
    if(valueEnd == -1) valueEnd = StringFind(jsonString, "}", valueStart);
    if(valueEnd == -1) return "";
    string value = StringSubstr(jsonString, valueStart, valueEnd - valueStart);
    value = StringTrimLeft(StringTrimRight(value));
    if(StringLen(value) > 0 && StringGetCharacter(value, 0) == '\"')
        value = StringSubstr(value, 1, StringLen(value) - 2);
    return value;
}

//+------------------------------------------------------------------+
//| Return all open positions as a JSON array                        |
//+------------------------------------------------------------------+
string getOpenPositions()
{
    string positions = "";
    for(int i = 0; i < OrdersTotal(); i++)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
            continue;

        int orderType = OrderType();
        if(orderType != OP_BUY && orderType != OP_SELL)
            continue;

        string orderTypeStr;
        double currentPrice;
        if(orderType == OP_BUY)
        {
            orderTypeStr = "BUY";
            currentPrice = MarketInfo(OrderSymbol(), MODE_BID);
        }
        else
        {
            orderTypeStr = "SELL";
            currentPrice = MarketInfo(OrderSymbol(), MODE_ASK);
        }

        string position = StringFormat(
            "{\"ticket\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,"
            "\"openPrice\":%.5f,\"curPrice\":%.5f,\"sl\":%.5f,\"tp\":%.5f}",
            OrderTicket(), OrderSymbol(), orderTypeStr, OrderLots(),
            OrderOpenPrice(), currentPrice, OrderStopLoss(), OrderTakeProfit()
        );

        if(positions != "") positions += ",";
        positions += position;
    }
    return "[" + positions + "]";
}

//+------------------------------------------------------------------+
//| Return closed trade history as a JSON object                     |
//+------------------------------------------------------------------+
string getTradeHistory(int startTime = 0, int endTime = 0, int specificTicket = 0)
{
    string result = "{\"status\":\"OK\",\"message\":\"\",\"trades\":[";
    int total = OrdersHistoryTotal();
    bool firstTrade = true;

    for(int i = 0; i < total; i++)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY))
            continue;
        if(startTime > 0 && OrderCloseTime() < startTime) continue;
        if(endTime   > 0 && OrderCloseTime() > endTime)   continue;
        if(specificTicket > 0 && OrderTicket() != specificTicket) continue;
        if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;

        if(!firstTrade) result += ",";
        firstTrade = false;

        string orderType = (OrderType() == OP_BUY) ? "BUY" : "SELL";
        result += "{";
        result += "\"ticket\":"       + IntegerToString(OrderTicket())          + ",";
        result += "\"symbol\":\""     + OrderSymbol()                           + "\",";
        result += "\"type\":\""       + orderType                               + "\",";
        result += "\"lots\":"         + DoubleToString(OrderLots(), 2)          + ",";
        result += "\"openPrice\":"    + DoubleToString(OrderOpenPrice(), 5)     + ",";
        result += "\"closePrice\":"   + DoubleToString(OrderClosePrice(), 5)    + ",";
        result += "\"openTime\":"     + IntegerToString(OrderOpenTime())        + ",";
        result += "\"closeTime\":"    + IntegerToString(OrderCloseTime())       + ",";
        result += "\"sl\":"           + DoubleToString(OrderStopLoss(), 5)      + ",";
        result += "\"tp\":"           + DoubleToString(OrderTakeProfit(), 5)    + ",";
        result += "\"profit\":"       + DoubleToString(OrderProfit(), 2)        + ",";
        result += "\"commission\":"   + DoubleToString(OrderCommission(), 2)    + ",";
        result += "\"swap\":"         + DoubleToString(OrderSwap(), 2)          + ",";
        result += "\"magicNumber\":"  + IntegerToString(OrderMagicNumber());
        result += "}";
    }

    result += "]}";
    return result;
}

//+------------------------------------------------------------------+
//| Return pending orders as a JSON array                            |
//+------------------------------------------------------------------+
string getPendingOrders()
{
    string orders = "";
    for(int i = 0; i < OrdersTotal(); i++)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
            continue;

        int orderType = OrderType();
        if(orderType < OP_BUYLIMIT || orderType > OP_SELLSTOP)
            continue;

        string orderTypeStr;
        switch(orderType)
        {
            case OP_BUYLIMIT:  orderTypeStr = "BUY_LIMIT";  break;
            case OP_SELLLIMIT: orderTypeStr = "SELL_LIMIT"; break;
            case OP_BUYSTOP:   orderTypeStr = "BUY_STOP";   break;
            case OP_SELLSTOP:  orderTypeStr = "SELL_STOP";  break;
            default:           orderTypeStr = "UNKNOWN";    break;
        }

        string order = StringFormat(
            "{\"ticket\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,"
            "\"price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"comment\":\"%s\",\"expiration\":\"%s\"}",
            OrderTicket(), OrderSymbol(), orderTypeStr, OrderLots(),
            OrderOpenPrice(), OrderStopLoss(), OrderTakeProfit(),
            OrderComment(), TimeToString(OrderExpiration())
        );

        if(orders != "") orders += ",";
        orders += order;
    }
    return "[" + orders + "]";
}

//+------------------------------------------------------------------+
//| Return all market-watch symbols as a JSON array                  |
//+------------------------------------------------------------------+
string getSymbols()
{
    Print("Getting symbols...");
    string symbols = "";
    int totalSymbols = SymbolsTotal(true);
    Print("Total symbols: ", totalSymbols);
    for(int i = 0; i < totalSymbols; i++)
    {
        string symbol = SymbolName(i, true);
        if(symbols != "") symbols += ",";
        symbols += "\"" + symbol + "\"";
    }
    string result = "[" + symbols + "]";
    Print("Symbols result: ", result);
    return result;
}

//+------------------------------------------------------------------+
//| Return detailed spec for one symbol as a JSON object             |
//+------------------------------------------------------------------+
string getSymbolInfo(string symbol)
{
    if(!SymbolSelect(symbol, true))
        return StringFormat("{\"error\":\"Symbol %s not found\"}", symbol);

    double bid           = MarketInfo(symbol, MODE_BID);
    double ask           = MarketInfo(symbol, MODE_ASK);
    double point         = MarketInfo(symbol, MODE_POINT);
    int    digits        = (int)MarketInfo(symbol, MODE_DIGITS);
    double spread        = MarketInfo(symbol, MODE_SPREAD);
    double stopLevel     = MarketInfo(symbol, MODE_STOPLEVEL);
    double lotSize       = MarketInfo(symbol, MODE_LOTSIZE);
    double tickValue     = MarketInfo(symbol, MODE_TICKVALUE);
    double tickSize      = MarketInfo(symbol, MODE_TICKSIZE);
    double minLot        = MarketInfo(symbol, MODE_MINLOT);
    double maxLot        = MarketInfo(symbol, MODE_MAXLOT);
    double lotStep       = MarketInfo(symbol, MODE_LOTSTEP);
    double swapLong      = MarketInfo(symbol, MODE_SWAPLONG);
    double swapShort     = MarketInfo(symbol, MODE_SWAPSHORT);
    int    swapType      = (int)MarketInfo(symbol, MODE_SWAPTYPE);
    double marginInit    = MarketInfo(symbol, MODE_MARGININIT);
    double marginMaint   = MarketInfo(symbol, MODE_MARGINMAINTENANCE);
    double marginRequired = MarketInfo(symbol, MODE_MARGINREQUIRED);
    int    tradeAllowed  = (int)MarketInfo(symbol, MODE_TRADEALLOWED);
    int    freezeLevel   = (int)MarketInfo(symbol, MODE_FREEZELEVEL);

    double leverage = 0;
    if(marginRequired > 0)
        leverage = (lotSize * bid) / marginRequired;

    double marginPct = 0;
    if(lotSize > 0 && bid > 0)
        marginPct = (marginRequired / (lotSize * bid)) * 100;

    string swapTypeStr;
    switch(swapType)
    {
        case 0: swapTypeStr = "points";          break;
        case 1: swapTypeStr = "base_currency";   break;
        case 2: swapTypeStr = "interest";        break;
        case 3: swapTypeStr = "margin_currency"; break;
        default: swapTypeStr = "unknown";        break;
    }

    string json = StringFormat(
        "{\"symbol\":\"%s\","
        "\"bid\":%.5f,\"ask\":%.5f,\"spread\":%.1f,\"digits\":%d,\"point\":%.6f,"
        "\"contract_size\":%.2f,\"tick_value\":%.4f,\"tick_size\":%.6f,"
        "\"min_lot\":%.2f,\"max_lot\":%.2f,\"lot_step\":%.2f,"
        "\"swap_long\":%.2f,\"swap_short\":%.2f,\"swap_type\":\"%s\","
        "\"margin_required\":%.2f,\"margin_init\":%.2f,\"margin_maintenance\":%.2f,"
        "\"margin_pct\":%.4f,\"leverage\":%.1f,"
        "\"stop_level\":%.0f,\"freeze_level\":%d,\"trade_allowed\":%s}",
        symbol, bid, ask, spread, digits, point,
        lotSize, tickValue, tickSize,
        minLot, maxLot, lotStep,
        swapLong, swapShort, swapTypeStr,
        marginRequired, marginInit, marginMaint,
        marginPct, leverage,
        stopLevel, freezeLevel,
        tradeAllowed ? "true" : "false"
    );

    Print("Symbol info for ", symbol, ": ", json);
    return json;
}

//+------------------------------------------------------------------+
//| Return info for all market-watch symbols as a JSON array         |
//+------------------------------------------------------------------+
string getAllSymbolsInfo()
{
    string symbols = "";
    int totalSymbols = SymbolsTotal(true);
    for(int i = 0; i < totalSymbols; i++)
    {
        string symbol = SymbolName(i, true);
        string info   = getSymbolInfo(symbol);
        if(symbols != "") symbols += ",";
        symbols += info;
    }
    return "[" + symbols + "]";
}

//+------------------------------------------------------------------+
//| Place a market order                                             |
//+------------------------------------------------------------------+
int createInstantOrder(string symbol, int orderType, double volume, double stopLoss, double takeProfit)
{
    double price    = (orderType == OP_BUY) ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
    int    slippage = 3;
    string comment  = "Instant Order";

    int ticket = OrderSend(symbol, orderType, volume, price, slippage, stopLoss, takeProfit, comment, MAGIC_NUMBER, 0, clrNONE);
    if(ticket < 0)
        Print("OrderSend failed with error #", GetLastError());
    return ticket;
}

//+------------------------------------------------------------------+
//| Place a pending order                                            |
//+------------------------------------------------------------------+
int createPendingOrder(string symbol, int orderType, double volume, double price, double stopLoss, double takeProfit)
{
    int    slippage = 3;
    string comment  = "Pending Order";

    int ticket = OrderSend(symbol, orderType, volume, price, slippage, stopLoss, takeProfit, comment, MAGIC_NUMBER, 0, clrNONE);
    if(ticket < 0)
        Print("OrderSend (Pending) failed with error #", GetLastError());
    return ticket;
}

//+------------------------------------------------------------------+
//| Map a timeframe string to ENUM_TIMEFRAMES                        |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES stringToTimeframe(string timeframeStr)
{
    if(timeframeStr == "PERIOD_M1")  return PERIOD_M1;
    if(timeframeStr == "PERIOD_M5")  return PERIOD_M5;
    if(timeframeStr == "PERIOD_M15") return PERIOD_M15;
    if(timeframeStr == "PERIOD_M30") return PERIOD_M30;
    if(timeframeStr == "PERIOD_H1")  return PERIOD_H1;
    if(timeframeStr == "PERIOD_H4")  return PERIOD_H4;
    if(timeframeStr == "PERIOD_D1")  return PERIOD_D1;
    if(timeframeStr == "PERIOD_W1")  return PERIOD_W1;
    if(timeframeStr == "PERIOD_MN1") return PERIOD_MN1;
    return PERIOD_CURRENT;
}

//+------------------------------------------------------------------+
//| Return OHLCV for a specific bar as a JSON fragment               |
//+------------------------------------------------------------------+
string getOHLCV(string symbol, ENUM_TIMEFRAMES timeframe, datetime time)
{
    int shift = iBarShift(symbol, timeframe, time, false);
    if(shift == -1) return "";

    double open    = iOpen(symbol,   timeframe, shift);
    double high    = iHigh(symbol,   timeframe, shift);
    double low     = iLow(symbol,    timeframe, shift);
    double close   = iClose(symbol,  timeframe, shift);
    double volume  = iVolume(symbol, timeframe, shift);
    datetime barTime = iTime(symbol, timeframe, shift);

    return StringFormat(
        "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f,\"time\":%d",
        open, high, low, close, volume, barTime
    );
}

//+------------------------------------------------------------------+
//| Return account summary as a JSON fragment                        |
//+------------------------------------------------------------------+
string getAccountInfo()
{
    double marginLevel = (AccountMargin() != 0) ? (AccountEquity() / AccountMargin() * 100) : 0;
    return StringFormat(
        "\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"freeMargin\":%.2f,\"marginLevel\":%.2f",
        AccountBalance(), AccountEquity(), AccountMargin(), AccountFreeMargin(), marginLevel
    );
}

//+------------------------------------------------------------------+
//| Return CCI signal string                                         |
//+------------------------------------------------------------------+
string getCCISignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    double cci = iCCI(symbol, timeframe, 14, PRICE_TYPICAL, 0);
    if(cci < -100) return "BUY";
    else if(cci > 100) return "SELL";
    else return "NONE";
}

//+------------------------------------------------------------------+
//| Return Bollinger Bands signal string                             |
//+------------------------------------------------------------------+
string getBollingerBandsSignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    double upperBand  = iBands(symbol, timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 0);
    double lowerBand  = iBands(symbol, timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 0);
    double closePrice = iClose(symbol, timeframe, 0);

    if(closePrice <= lowerBand) return "BUY";
    else if(closePrice >= upperBand) return "SELL";
    else return "NONE";
}

//+------------------------------------------------------------------+
//| Return MACD signal string                                        |
//+------------------------------------------------------------------+
string getMACDSignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    double macd   = iMACD(symbol, timeframe, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   0);
    double signal = iMACD(symbol, timeframe, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);

    if(macd > signal)      return "BUY";
    else if(macd < signal) return "SELL";
    else return "NONE";
}

//+------------------------------------------------------------------+
//| Combine CCI + BB + MACD into a signals JSON fragment             |
//+------------------------------------------------------------------+
string getTradingSignals(string symbol, ENUM_TIMEFRAMES timeframe)
{
    return StringFormat(
        "{\"cci_signal\":\"%s\",\"bb_signal\":\"%s\",\"macd_signal\":\"%s\"}",
        getCCISignal(symbol, timeframe),
        getBollingerBandsSignal(symbol, timeframe),
        getMACDSignal(symbol, timeframe)
    );
}

//+------------------------------------------------------------------+
//| Calculate VWAP over the last 20 bars for the given symbol        |
//| Uses iHigh/iLow/iClose/iVolume so it works for any symbol, not  |
//| just the chart symbol.                                           |
//+------------------------------------------------------------------+
double calculateVWAP(string symbol, ENUM_TIMEFRAMES timeframe)
{
    double cumTypicalPrice = 0;
    double cumVolume       = 0;

    for(int i = 0; i < 20; i++)
    {
        double typicalPrice = (iHigh(symbol, timeframe, i) +
                               iLow(symbol,  timeframe, i) +
                               iClose(symbol, timeframe, i)) / 3.0;
        double vol = (double)iVolume(symbol, timeframe, i);
        cumTypicalPrice += typicalPrice * vol;
        cumVolume       += vol;
    }

    return (cumVolume > 0) ? cumTypicalPrice / cumVolume : iClose(symbol, timeframe, 0);
}

//+------------------------------------------------------------------+
//| IsMarketOpen — checks broker session hours for the given symbol  |
//+------------------------------------------------------------------+
bool IsMarketOpen(string symbol)
{
    datetime serverTime = TimeCurrent();
    int dayOfWeek  = TimeDayOfWeek(serverTime);
    int hour       = TimeHour(serverTime);
    int minute     = TimeMinute(serverTime);
    int currentTime = hour * 100 + minute; // HHMM format

    Print("Current server time: ", TimeToStr(serverTime),
          " (Day: ", dayOfWeek,
          ", HHMM: ", currentTime, ")");

    switch(dayOfWeek)
    {
        case 1: // Monday
        case 2: // Tuesday
        case 3: // Wednesday
        case 4: // Thursday
            if((currentTime >= 0 && currentTime <= 2159) ||
               (currentTime >= 2301 && currentTime <= 2400))
            {
                double bid = MarketInfo(symbol, MODE_BID);
                double ask = MarketInfo(symbol, MODE_ASK);
                if(bid == 0 || ask == 0 || bid == EMPTY_VALUE || ask == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask for ", symbol);
                    return false;
                }
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: SymbolSelect failed for ", symbol);
                    return false;
                }
                return true;
            }
            break;

        case 5: // Friday
            if(currentTime >= 0 && currentTime <= 2159)
            {
                double bid = MarketInfo(symbol, MODE_BID);
                double ask = MarketInfo(symbol, MODE_ASK);
                if(bid == 0 || ask == 0 || bid == EMPTY_VALUE || ask == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask for ", symbol);
                    return false;
                }
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: SymbolSelect failed for ", symbol);
                    return false;
                }
                return true;
            }
            break;

        case 0: // Sunday
            if(currentTime >= 2301 && currentTime <= 2400)
            {
                double bid = MarketInfo(symbol, MODE_BID);
                double ask = MarketInfo(symbol, MODE_ASK);
                if(bid == 0 || ask == 0 || bid == EMPTY_VALUE || ask == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask for ", symbol);
                    return false;
                }
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: SymbolSelect failed for ", symbol);
                    return false;
                }
                return true;
            }
            break;
    }

    Print("Market closed: No valid trading session for ", symbol, " at HHMM=", currentTime);
    return false;
}

//+------------------------------------------------------------------+
//| Send a real-time streaming update for g_symbols[symbolIndex]    |
//|                                                                  |
//| All indicator calls use explicit (symbol, timeframe, ...) forms  |
//| so this function works correctly for any symbol, not just the    |
//| chart symbol.  The only remaining chart-level dependency was     |
//| the Fibonacci high/low using High[]/Low[] arrays — those now     |
//| use iHigh()/iLow() with the correct symbol argument.            |
//+------------------------------------------------------------------+
void sendRealTimeUpdate(int symbolIndex)
{
    string symbol = g_symbols[symbolIndex];

    // Market-open check
    bool isMarketOpen = IsMarketOpen(symbol);

    // Require at least 50 bars for all indicators
    int availBars = iBars(symbol, g_timeframe);
    int requiredBars = 200; // MA_200 needs 200 bars
    if(availBars < requiredBars)
    {
        Print("Not enough bars for ", symbol, ". Required: ", requiredBars, ", Available: ", availBars);
        return;
    }

    // ---- Technical Indicators (all with explicit symbol parameter) ----
    double MA_20   = iMA(symbol, g_timeframe, 20,  0, MODE_SMA, PRICE_CLOSE, 0);
    double MA_50   = iMA(symbol, g_timeframe, 50,  0, MODE_SMA, PRICE_CLOSE, 0);
    double MA_200  = iMA(symbol, g_timeframe, 200, 0, MODE_SMA, PRICE_CLOSE, 0);
    double RSI_14  = iRSI(symbol, g_timeframe, 14, PRICE_CLOSE, 0);
    double MACD_main   = iMACD(symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   0);
    double MACD_signal = iMACD(symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
    double BB_upper    = iBands(symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 0);
    double BB_middle   = iBands(symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN,  0);
    double BB_lower    = iBands(symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 0);
    double ATR         = iATR(symbol, g_timeframe, 14, 0);
    double SAR         = iSAR(symbol, g_timeframe, 0.02, 0.2, 0);
    double VWAP        = calculateVWAP(symbol, g_timeframe);

    // OHLCV for current bar
    string priceData = getOHLCV(symbol, g_timeframe, TimeCurrent());
    if(StringLen(priceData) == 0)
    {
        Print("Invalid price data for ", symbol, ". Skipping update.");
        return;
    }

    // Validate indicators
    if(MA_20 == EMPTY_VALUE || MA_50 == EMPTY_VALUE || MA_200 == EMPTY_VALUE ||
       RSI_14 == EMPTY_VALUE ||
       MACD_main == EMPTY_VALUE || MACD_signal == EMPTY_VALUE ||
       BB_upper == EMPTY_VALUE  || BB_middle == EMPTY_VALUE || BB_lower == EMPTY_VALUE)
    {
        Print("One or more indicators returned EMPTY_VALUE for ", symbol, ". Skipping update.");
        return;
    }

    // ---- Fibonacci levels (20-bar swing high/low) ----
    // Use iHigh/iLow with explicit symbol so non-chart symbols work correctly
    int highIdx = iHighest(symbol, g_timeframe, MODE_HIGH, 20, 0);
    int lowIdx  = iLowest(symbol,  g_timeframe, MODE_LOW,  20, 0);
    double swingHigh = iHigh(symbol, g_timeframe, highIdx);
    double swingLow  = iLow(symbol,  g_timeframe, lowIdx);

    double fib_236 = swingHigh - ((swingHigh - swingLow) * 0.236);
    double fib_382 = swingHigh - ((swingHigh - swingLow) * 0.382);
    double fib_500 = swingHigh - ((swingHigh - swingLow) * 0.500);
    double fib_618 = swingHigh - ((swingHigh - swingLow) * 0.618);
    double fib_786 = swingHigh - ((swingHigh - swingLow) * 0.786);

    // ---- Signals ----
    string signals = getTradingSignals(symbol, g_timeframe);

    // ---- Compose TA indicators JSON fragment ----
    string taIndicators = StringFormat(
        "\"MA_20\":%.5f,\"MA_50\":%.5f,\"MA_200\":%.5f,"
        "\"RSI_14\":%.2f,"
        "\"MACD\":%.5f,\"MACD_signal\":%.5f,"
        "\"BB_upper\":%.5f,\"BB_middle\":%.5f,\"BB_lower\":%.5f,"
        "\"ATR\":%.5f,\"SAR\":%.5f,\"VWAP\":%.5f,"
        "\"FIB_236\":%.5f,\"FIB_382\":%.5f,\"FIB_500\":%.5f,"
        "\"FIB_618\":%.5f,\"FIB_786\":%.5f,"
        "\"FIB_HIGH\":%.5f,\"FIB_LOW\":%.5f",
        MA_20, MA_50, MA_200,
        RSI_14,
        MACD_main, MACD_signal,
        BB_upper, BB_middle, BB_lower,
        ATR, SAR, VWAP,
        fib_236, fib_382, fib_500, fib_618, fib_786,
        swingHigh, swingLow
    );

    // ---- Full message ----
    string message = StringFormat(
        "{\"type\":\"real_time_update\",\"symbol\":\"%s\",\"timeframe\":%d,"
        "\"market_open\":%s,\"price_data\":{%s},\"signals\":%s,\"ta_indicators\":{%s}}",
        symbol,
        (int)g_timeframe,
        isMarketOpen ? "true" : "false",
        priceData,
        signals,
        taIndicators
    );

    ZmqMsg updateMsg(message);
    if(!pubSocket.send(updateMsg))
        Print("Error: Failed to send real-time update for ", symbol);
    else
        Print("Sent update for ", symbol, ": ", StringSubstr(message, 0, 120), "...");
}

//+------------------------------------------------------------------+
//| Periodic debug heartbeat                                         |
//+------------------------------------------------------------------+
void sendTestMessage()
{
    string message = "{\"type\":\"test_message\",\"content\":\"Hello from MT4!\"}";
    ZmqMsg testMsg(message);
    if(!pubSocket.send(testMsg))
        Print("Error: Failed to send test message.");
    else
        Print("Sent test message: ", message);
}
