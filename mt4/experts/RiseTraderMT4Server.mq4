//+------------------------------------------------------------------+
//|                                      ExpertsRiseTraderServer.mq4 |
//|                                   Copyright 2025, Tuniverse Ltd. |
//|                                       https://www.tuniverses.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2025, Tuniverse Ltd."
#property link      "https://www.tuniverses.com"
#property version   "1.00"
#property strict

// Import ZMQ library (requires mql-zmq library installation)
// Download from: https://github.com/dingmaotu/mql-zmq
#include <ZMQ/Zmq.mqh>

// Define a unique magic number for your EA
#define MAGIC_NUMBER 123456

// Global variables
Context context("helloworld");
Socket repSocket(context, ZMQ_REP);      // Renamed for clarity
Socket pubSocket(context, ZMQ_PUB);      // Renamed for clarity
string g_symbol = "CrudeOIL";            // Ensure this symbol exists in your MT4
ENUM_TIMEFRAMES g_timeframe = PERIOD_M1; // Changed to ENUM_TIMEFRAMES for type safety
datetime g_lastUpdateTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // Set timer for every 1 second to handle ZMQ requests frequently
    EventSetTimer(1);  // Changed from 60 to 1 for more responsive request handling

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
        repSocket.unbind("tcp://*:5555"); // Clean up REP socket if PUB binding fails
        return(INIT_FAILED);
    }

    // Validate the symbol
    if(!SymbolSelect(g_symbol, true))
    {
        Print("Error: Symbol ", g_symbol, " not found or failed to load.");
        repSocket.unbind("tcp://*:5555");
        pubSocket.unbind("tcp://*:5556");
        return(INIT_FAILED);
    }

    // Initialize lastBarTime
    g_lastUpdateTime = iTime(g_symbol, g_timeframe, 0);

    Print("MT4 Server Initialized and ZMQ Sockets Bound.");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    // Kill the timer
    EventKillTimer();

    // Attempt to unbind REP socket
    if(!repSocket.unbind("tcp://*:5555"))
    {
        Print("Warning: Failed to unbind REP socket.");
    }

    // Attempt to unbind PUB socket
    if(!pubSocket.unbind("tcp://*:5556"))
    {
        Print("Warning: Failed to unbind PUB socket.");
    }

    Print("MT4 Server Deinitialized and ZMQ Sockets Closed.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    datetime currentBarTime = iTime(g_symbol, g_timeframe, 0);
    if(currentBarTime != g_lastUpdateTime)
    {
        sendRealTimeUpdate();
        g_lastUpdateTime = currentBarTime;
    }
}

//+------------------------------------------------------------------+
//| Timer function to handle ZeroMQ requests and send fallback updates|
//+------------------------------------------------------------------+
void OnTimer()
{
    // Handle incoming ZMQ requests
    handleZmqRequests();

    // Send fallback updates every minute
    if(TimeCurrent() - g_lastUpdateTime >= 60)
    {
        sendRealTimeUpdate();
        g_lastUpdateTime = TimeCurrent();
    }

    // Optional: Send a test message every 5 minutes for debugging
    if(TimeMinute(TimeCurrent()) % 5 == 0 && TimeSeconds(TimeCurrent()) == 0)
    {
        sendTestMessage();
    }
}

//+------------------------------------------------------------------+
//| Function to handle ZeroMQ requests                              |
//+------------------------------------------------------------------+
void handleZmqRequests()
{
    ZmqMsg request;

    // Continuously receive all pending requests without blocking
    while(repSocket.recv(request, ZMQ_DONTWAIT))
    {
        string requestString = request.getData();
        Print("Received request: ", requestString);

        string response = processRequest(requestString);

        // Send reply
        ZmqMsg replyMsg(response);
        if(!repSocket.send(replyMsg))
        {
            Print("Error: Failed to send reply for request: ", requestString);
        }
        else
        {
            Print("Reply sent: ", response);
        }
    }
}

//+------------------------------------------------------------------+
//| Function to process incoming requests                            |
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
        // Implement actual login logic with security measures
        response = createJsonResponse("OK", "Login successful");
    }
    else if(command == "loadPair")
    {
        string symbol = extractValue(requestString, "symbol");
        if(SymbolSelect(symbol, true))
        {
            response = createJsonResponse("OK", StringFormat("Symbol %s loaded", symbol));
        }
        else
        {
            response = createJsonResponse("ERROR", StringFormat("Failed to load symbol %s", symbol));
        }
    }
    else if(command == "iClose" || command == "iOpen" || command == "iHigh" || command == "iLow" || command == "iTime" || command == "iVolume")
    {
        string symbol = extractValue(requestString, "symbol");
        string timeframeStr = extractValue(requestString, "timeframe");
        string timeStr = extractValue(requestString, "time");

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
            if(command == "iClose")
                value = iClose(symbol, timeframe, shift);
            else if(command == "iOpen")
                value = iOpen(symbol, timeframe, shift);
            else if(command == "iHigh")
                value = iHigh(symbol, timeframe, shift);
            else if(command == "iLow")
                value = iLow(symbol, timeframe, shift);
            else if(command == "iTime")
                value = (double)iTime(symbol, timeframe, shift);
            else if(command == "iVolume")
                value = (double)iVolume(symbol, timeframe, shift);

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
        string symbol = extractValue(requestString, "symbol");
        string timeframeStr = extractValue(requestString, "timeframe");
        string timeStr = extractValue(requestString, "time");

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
    else if(command == "get_symbols")
    {
        string symbols = getSymbols();
        response = createJsonResponse("OK", "", StringFormat("\"symbols\":%s", symbols));
    }
    else if(command == "create_instant_order")
    {
        string symbol = extractValue(requestString, "symbol");
        string orderTypeStr = extractValue(requestString, "order_type");
        string volumeStr = extractValue(requestString, "volume");
        string stopLossStr = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");

        // Convert strings to appropriate types
        int orderType;
        if(orderTypeStr == "BUY")
            orderType = OP_BUY;
        else if(orderTypeStr == "SELL")
            orderType = OP_SELL;
        else
        {
            response = createJsonResponse("ERROR", "Invalid order type.");
            Print("Invalid order type received: ", orderTypeStr);
            return response;
        }

        double volume = StringToDouble(volumeStr);
        double stopLoss = StringToDouble(stopLossStr);
        double takeProfit = StringToDouble(takeProfitStr);

        int ticket = createInstantOrder(symbol, orderType, volume, stopLoss, takeProfit);
        if(ticket > 0)
            response = createJsonResponse("OK", StringFormat("Order created with ticket %d", ticket));
        else
            response = createJsonResponse("ERROR", StringFormat("Failed to create order. Error: %d", GetLastError()));
    }
    else if(command == "create_pending_order")
    {
        string symbol = extractValue(requestString, "symbol");
        string orderTypeStr = extractValue(requestString, "order_type");
        string volumeStr = extractValue(requestString, "volume");
        string priceStr = extractValue(requestString, "price");
        string stopLossStr = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");

        // Convert strings to appropriate types
        int orderType;
        if(orderTypeStr == "BUY_LIMIT")
            orderType = OP_BUYLIMIT;
        else if(orderTypeStr == "SELL_LIMIT")
            orderType = OP_SELLLIMIT;
        else if(orderTypeStr == "BUY_STOP")
            orderType = OP_BUYSTOP;
        else if(orderTypeStr == "SELL_STOP")
            orderType = OP_SELLSTOP;
        else
        {
            response = createJsonResponse("ERROR", "Invalid pending order type.");
            Print("Invalid pending order type received: ", orderTypeStr);
            return response;
        }

        double volume = StringToDouble(volumeStr);
        double price = StringToDouble(priceStr);
        double stopLoss = StringToDouble(stopLossStr);
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
        // Modify SL/TP of an open position (for institutional stop-hunting avoidance)
        string ticketStr = extractValue(requestString, "ticket");
        string stopLossStr = extractValue(requestString, "stop_loss");
        string takeProfitStr = extractValue(requestString, "take_profit");
        
        int ticket = StringToInteger(ticketStr);
        double newStopLoss = StringToDouble(stopLossStr);
        double newTakeProfit = StringToDouble(takeProfitStr);
        
        if(OrderSelect(ticket, SELECT_BY_TICKET))
        {
            // Only modify market orders (BUY/SELL), not pending orders
            int orderType = OrderType();
            if(orderType == OP_BUY || orderType == OP_SELL)
            {
                // Use existing values if new values are 0 or not provided
                double sl = (newStopLoss > 0) ? newStopLoss : OrderStopLoss();
                double tp = (newTakeProfit > 0) ? newTakeProfit : OrderTakeProfit();
                
                bool result = OrderModify(ticket, OrderOpenPrice(), sl, tp, 0, clrNONE);
                if(result)
                    response = createJsonResponse("OK", StringFormat("Position %d modified: SL=%.5f, TP=%.5f", ticket, sl, tp));
                else
                    response = createJsonResponse("ERROR", StringFormat("Failed to modify position %d. Error: %d", ticket, GetLastError()));
            }
            else
            {
                response = createJsonResponse("ERROR", StringFormat("Ticket %d is a pending order, not an open position. Use modify_pending_order instead.", ticket));
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
            // Check if it's actually a pending order
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
//| Function to create a JSON string                                 |
//+------------------------------------------------------------------+
string createJsonResponse(string status, string message, string additional = "")
{
    if (additional == "")
        return StringFormat("{\"status\":\"%s\",\"message\":\"%s\"}", status, message);
    else
        return StringFormat("{\"status\":\"%s\",\"message\":\"%s\",%s}", status, message, additional);
}

//+------------------------------------------------------------------+
//| Simple function to extract value from JSON-like string           |
//+------------------------------------------------------------------+
string extractValue(string jsonString, string key)
{
    int keyPos = StringFind(jsonString, "\"" + key + "\"");
    if (keyPos == -1) return "";
    int colonPos = StringFind(jsonString, ":", keyPos);
    if (colonPos == -1) return "";
    int valueStart = colonPos + 1;
    int valueEnd = StringFind(jsonString, ",", valueStart);
    if (valueEnd == -1) valueEnd = StringFind(jsonString, "}", valueStart);
    if (valueEnd == -1) return ""; // Prevent error if neither ',' nor '}' is found
    string value = StringSubstr(jsonString, valueStart, valueEnd - valueStart);
    value = StringTrimLeft(StringTrimRight(value));
    if (StringLen(value) > 0 && StringGetCharacter(value, 0) == '\"')
        value = StringSubstr(value, 1, StringLen(value) - 2);
    return value;
}

//+------------------------------------------------------------------+
//| Function to get open positions                                   |
//+------------------------------------------------------------------+
string getOpenPositions()
{
    string positions = "";
    for(int i = 0; i < OrdersTotal(); i++)
    {
        if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
            // Only include market orders (BUY/SELL), not pending orders
            int orderType = OrderType();
            if(orderType != OP_BUY && orderType != OP_SELL)
                continue;
                
            string orderTypeStr;
            switch(orderType)
            {
                case OP_BUY: orderTypeStr = "BUY"; break;
                case OP_SELL: orderTypeStr = "SELL"; break;
                default: orderTypeStr = "OTHER"; break;
            }

            string position = StringFormat(
                "{\"ticket\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,\"openPrice\":%.5f,\"curPrice\":%.5f,\"sl\":%.5f,\"tp\":%.5f}",
                OrderTicket(), OrderSymbol(), orderTypeStr, OrderLots(), OrderOpenPrice(), OrderClosePrice(), OrderStopLoss(), OrderTakeProfit()
            );

            if(positions != "") positions += ",";
            positions += position;
        }
    }
    return "[" + positions + "]";
}

//+------------------------------------------------------------------+
//| Function to get pending orders                                    |
//+------------------------------------------------------------------+
string getPendingOrders()
{
    string orders = "";
    for(int i = 0; i < OrdersTotal(); i++)
    {
        if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
            int orderType = OrderType();
            
            // Only include pending orders (BUYLIMIT, SELLLIMIT, BUYSTOP, SELLSTOP)
            if(orderType < OP_BUYLIMIT || orderType > OP_SELLSTOP)
                continue;
            
            string orderTypeStr;
            switch(orderType)
            {
                case OP_BUYLIMIT: orderTypeStr = "BUY_LIMIT"; break;
                case OP_SELLLIMIT: orderTypeStr = "SELL_LIMIT"; break;
                case OP_BUYSTOP: orderTypeStr = "BUY_STOP"; break;
                case OP_SELLSTOP: orderTypeStr = "SELL_STOP"; break;
                default: orderTypeStr = "UNKNOWN"; break;
            }

            string order = StringFormat(
                "{\"ticket\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,\"price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"comment\":\"%s\",\"expiration\":\"%s\"}",
                OrderTicket(), OrderSymbol(), orderTypeStr, OrderLots(), OrderOpenPrice(), 
                OrderStopLoss(), OrderTakeProfit(), OrderComment(), TimeToString(OrderExpiration())
            );

            if(orders != "") orders += ",";
            orders += order;
        }
    }
    return "[" + orders + "]";
}

//+------------------------------------------------------------------+
//| Function to get all available symbols                            |
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
        Print("Symbol ", i, ": ", symbol);
        if(symbols != "") symbols += ",";
        symbols += "\"" + symbol + "\"";
    }
    string result = "[" + symbols + "]";
    Print("Symbols result: ", result);
    return result;
}

//+------------------------------------------------------------------+
//| Function to create an instant order                              |
//+------------------------------------------------------------------+
int createInstantOrder(string symbol, int orderType, double volume, double stopLoss, double takeProfit)
{
    double price = (orderType == OP_BUY) ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
    int slippage = 3;
    string comment = "Instant Order";

    int ticket = OrderSend(symbol, orderType, volume, price, slippage, stopLoss, takeProfit, comment, MAGIC_NUMBER, 0, clrNONE);
    if(ticket < 0)
    {
        Print("OrderSend failed with error #", GetLastError());
    }
    return ticket;
}

//+------------------------------------------------------------------+
//| Function to create a pending order                              |
//+------------------------------------------------------------------+
int createPendingOrder(string symbol, int orderType, double volume, double price, double stopLoss, double takeProfit)
{
    int slippage = 3;
    string comment = "Pending Order";

    int ticket = OrderSend(symbol, orderType, volume, price, slippage, stopLoss, takeProfit, comment, MAGIC_NUMBER, 0, clrNONE);
    if(ticket < 0)
    {
        Print("OrderSend (Pending) failed with error #", GetLastError());
    }
    return ticket;
}

//+------------------------------------------------------------------+
//| Function to convert string timeframe to ENUM_TIMEFRAMES          |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES stringToTimeframe(string timeframeStr)
{
    if(timeframeStr == "PERIOD_M1")   return PERIOD_M1;
    if(timeframeStr == "PERIOD_M5")   return PERIOD_M5;
    if(timeframeStr == "PERIOD_M15")  return PERIOD_M15;
    if(timeframeStr == "PERIOD_M30")  return PERIOD_M30;
    if(timeframeStr == "PERIOD_H1")   return PERIOD_H1;
    if(timeframeStr == "PERIOD_H4")   return PERIOD_H4;
    if(timeframeStr == "PERIOD_D1")   return PERIOD_D1;
    if(timeframeStr == "PERIOD_W1")   return PERIOD_W1;
    if(timeframeStr == "PERIOD_MN1")  return PERIOD_MN1;
    return PERIOD_CURRENT; // Default to current timeframe if not recognized
}

//+------------------------------------------------------------------+
//| Function to get OHLCV data for a specific bar                     |
//+------------------------------------------------------------------+
string getOHLCV(string symbol, ENUM_TIMEFRAMES timeframe, datetime time)
{
    int shift = iBarShift(symbol, timeframe, time, false);
    if(shift == -1) return "";
    
    double open = iOpen(symbol, timeframe, shift);
    double high = iHigh(symbol, timeframe, shift);
    double low = iLow(symbol, timeframe, shift);
    double close = iClose(symbol, timeframe, shift);
    double volume = iVolume(symbol, timeframe, shift);
    datetime barTime = iTime(symbol, timeframe, shift);

    // Convert broker time to UTC
    datetime utcTime = barTime;
    datetime pstTime = barTime - TimeGMTOffset();
    
    // Debug print
    //Print("Bar Time (Broker): ", TimeToString(barTime));
    //Print("GMT Offset: ", TimeGMTOffset());
    //Print("UTC Time: ", TimeToString(utcTime));
    //Print("PST Time: ", TimeToString(pstTime));

    // barTime is already in UTC, no conversion needed
    return StringFormat(
        "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f,\"time\":%d",
        open, high, low, close, volume, barTime
    );
}

//+------------------------------------------------------------------+
//| Function to get account information                              |
//+------------------------------------------------------------------+
string getAccountInfo()
{
    double marginLevel = (AccountMargin() != 0) ? (AccountEquity() / AccountMargin() * 100) : 0;
    return StringFormat("\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"freeMargin\":%.2f,\"marginLevel\":%.2f",
                        AccountBalance(), AccountEquity(), AccountMargin(), AccountFreeMargin(), marginLevel);
}

//+------------------------------------------------------------------+
//| New function to get CCI signal                                   |
//+------------------------------------------------------------------+
string getCCISignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    int cciPeriod = 14;
    double cci = iCCI(symbol, timeframe, cciPeriod, PRICE_TYPICAL, 0);

    if(cci < -100) return "BUY";
    else if(cci > 100) return "SELL";
    else return "NONE";
}

//+------------------------------------------------------------------+
//| New function to get Bollinger Bands signal                       |
//+------------------------------------------------------------------+
string getBollingerBandsSignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    int bbPeriod = 20;
    double deviation = 2.0;
    double upperBand = iBands(symbol, timeframe, bbPeriod, deviation, 0, PRICE_CLOSE, MODE_UPPER, 0);
    double lowerBand = iBands(symbol, timeframe, bbPeriod, deviation, 0, PRICE_CLOSE, MODE_LOWER, 0);
    double closePrice = iClose(symbol, timeframe, 0);

    if(closePrice <= lowerBand) return "BUY";
    else if(closePrice >= upperBand) return "SELL";
    else return "NONE";
}



//+------------------------------------------------------------------+
//| New function to get calculate VWAP                       |
//+------------------------------------------------------------------+
double calculateVWAP()
{
    double cumTypicalPrice = 0;
    double cumVolume = 0;
    
    for(int i = 0; i < 20; i++)  // Calculate VWAP for last 20 bars
    {
        double typicalPrice = (High[i] + Low[i] + Close[i]) / 3;
        cumTypicalPrice += typicalPrice * Volume[i];
        cumVolume += Volume[i];
    }
    
    return cumVolume > 0 ? cumTypicalPrice / cumVolume : Close[0];
}

//+------------------------------------------------------------------+
//| New function to get MACD signal                                   |
//+------------------------------------------------------------------+
string getMACDSignal(string symbol, ENUM_TIMEFRAMES timeframe)
{
    int fastEMA = 12;
    int slowEMA = 26;
    int signalSMA = 9;
    double macd = iMACD(symbol, timeframe, fastEMA, slowEMA, signalSMA, PRICE_CLOSE, MODE_MAIN, 0);
    double signal = iMACD(symbol, timeframe, fastEMA, slowEMA, signalSMA, PRICE_CLOSE, MODE_SIGNAL, 0);

    if(macd > signal) return "BUY";
    else if(macd < signal) return "SELL";
    else return "NONE";
}

//+------------------------------------------------------------------+
//| New function to combine signals                                  |
//+------------------------------------------------------------------+
string getTradingSignals(string symbol, ENUM_TIMEFRAMES timeframe)
{
    string cciSignal = getCCISignal(symbol, timeframe);
    string bbSignal = getBollingerBandsSignal(symbol, timeframe);
    string macdSignal = getMACDSignal(symbol, timeframe);

    string signals = StringFormat("{\"cci_signal\":\"%s\",\"bb_signal\":\"%s\",\"macd_signal\":\"%s\"}", 
                                  cciSignal, bbSignal, macdSignal);
    return signals;
}

//+------------------------------------------------------------------+
//| Function to check if market is open                               |
//+------------------------------------------------------------------+
//bool IsMarketOpen(string symbol)
//{
    // Get current server time
//    datetime serverTime = TimeCurrent();
    
    // Check if it's weekend
//    int dayOfWeek = TimeDayOfWeek(serverTime);
//    if(dayOfWeek == 0 || dayOfWeek == 6)
//        return false;
        
    // Check if symbol is actually trading
//    double currentBid = MarketInfo(symbol, MODE_BID);
 //   double currentAsk = MarketInfo(symbol, MODE_ASK);
    
    // If either bid or ask is 0 or invalid, market is likely closed
//    if(currentBid == 0 || currentAsk == 0 || currentBid == EMPTY_VALUE || currentAsk == EMPTY_VALUE)
 //       return false;
        
    // Check if symbol is selected/available
//    if(!SymbolSelect(symbol, true))
//        return false;
        
    // If we got here, market should be open
//    return true;
//}

bool IsMarketOpen(string symbol)
{
    // Get current server time
    datetime serverTime = TimeCurrent();
    
    // Check if it's weekend
    int dayOfWeek = TimeDayOfWeek(serverTime);
    if(dayOfWeek == 0 || dayOfWeek == 6)
    {
        Print("Market closed: Weekend (Day ", dayOfWeek, " - ", 
              dayOfWeek == 0 ? "Sunday" : "Saturday", 
              "), except for specific Sunday hours");
    }
        
    // Get current hour and minute
    int hour = TimeHour(serverTime);
    int minute = TimeMinute(serverTime);
    int currentTime = hour * 100 + minute;  // Convert to HHMM format
    
    Print("Current server time: ", TimeToStr(serverTime), 
          " (Day: ", dayOfWeek, 
          ", Hour: ", hour, 
          ", Minute: ", minute, 
          ", HHMM: ", currentTime, ")");
    
    // Check trading sessions based on day of week
    switch(dayOfWeek)
    {
        case 1: // Monday
        case 2: // Tuesday
        case 3: // Wednesday
        case 4: // Thursday
            // Trading hours: 00:00-21:59, 23:01-24:00
            if((currentTime >= 0 && currentTime <= 2159) || 
               (currentTime >= 2301 && currentTime <= 2400))
            {
                Print("Market should be open: Regular trading day within valid hours");
                
                // Additional safety checks
                double currentBid = MarketInfo(symbol, MODE_BID);
                double currentAsk = MarketInfo(symbol, MODE_ASK);
                
                Print("Current Bid: ", currentBid, ", Ask: ", currentAsk);
                
                if(currentBid == 0 || currentAsk == 0 || currentBid == EMPTY_VALUE || currentAsk == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask prices despite being within trading hours");
                    return false;
                }
                
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: Symbol selection failed");
                    return false;
                }
                
                return true;
            }
            else
            {
                Print("Market closed: Outside trading hours for weekday (", currentTime, 
                      "). Valid hours are 00:00-21:59 and 23:01-24:00");
            }
            break;
            
        case 5: // Friday
            // Trading hours: 00:00-21:59
            if(currentTime >= 0 && currentTime <= 2159)
            {
                Print("Market should be open: Friday within valid hours");
                
                // Additional safety checks
                double currentBid = MarketInfo(symbol, MODE_BID);
                double currentAsk = MarketInfo(symbol, MODE_ASK);
                
                Print("Current Bid: ", currentBid, ", Ask: ", currentAsk);
                
                if(currentBid == 0 || currentAsk == 0 || currentBid == EMPTY_VALUE || currentAsk == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask prices despite being within trading hours");
                    return false;
                }
                
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: Symbol selection failed");
                    return false;
                }
                
                return true;
            }
            else
            {
                Print("Market closed: Outside trading hours for Friday (", currentTime, 
                      "). Valid hours are 00:00-21:59");
            }
            break;
            
        case 0: // Sunday
            // Trading hours: 23:01-24:00
            if(currentTime >= 2301 && currentTime <= 2400)
            {
                Print("Market should be open: Sunday within valid hours");
                
                // Additional safety checks
                double currentBid = MarketInfo(symbol, MODE_BID);
                double currentAsk = MarketInfo(symbol, MODE_ASK);
                
                Print("Current Bid: ", currentBid, ", Ask: ", currentAsk);
                
                if(currentBid == 0 || currentAsk == 0 || currentBid == EMPTY_VALUE || currentAsk == EMPTY_VALUE)
                {
                    Print("Market closed: Invalid Bid/Ask prices despite being within trading hours");
                    return false;
                }
                
                if(!SymbolSelect(symbol, true))
                {
                    Print("Market closed: Symbol selection failed");
                    return false;
                }
                
                return true;
            }
            else
            {
                Print("Market closed: Outside trading hours for Sunday (", currentTime, 
                      "). Valid hours are 23:01-24:00");
            }
            break;
    }
    
    // Additional safety checks for logging purposes
    double finalBid = MarketInfo(symbol, MODE_BID);
    double finalAsk = MarketInfo(symbol, MODE_ASK);
    Print("Final check - Bid: ", finalBid, ", Ask: ", finalAsk);
    
    if(!SymbolSelect(symbol, true))
    {
        Print("Final check - Symbol selection failed");
    }
    
    Print("Market closed: No valid trading session found");
    return false;
}

//+------------------------------------------------------------------+
//| Function to send real-time updates including price data and signals|
//+------------------------------------------------------------------+
void sendRealTimeUpdate()
{

    // Add market open check at the start
    bool isMarketOpen = IsMarketOpen(g_symbol);
          
    // Ensure there are enough bars to calculate indicators
    int requiredBars = MathMax(50, 26); // 50 for MA_50 and 26 for MACD slow EMA
    if(Bars < requiredBars)
    {
        Print("Not enough bars to calculate all indicators. Required: ", requiredBars, ", Available: ", Bars);
        return;
    }
    
    // Calculate Technical Indicators
    double MA_20 = iMA(g_symbol, g_timeframe, 20, 0, MODE_SMA, PRICE_CLOSE, 0);
    double MA_50 = iMA(g_symbol, g_timeframe, 50, 0, MODE_SMA, PRICE_CLOSE, 0);
    
    // Calculate MA_200
    double MA_200 = iMA(g_symbol, g_timeframe, 200, 0, MODE_SMA, PRICE_CLOSE, 0);
    
    // Calculate RSI
    double RSI_14 = iRSI(g_symbol, g_timeframe, 14, PRICE_CLOSE, 0);
    
    // Calculate MACD Components
    double MACD_main = iMACD(g_symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 0);
    double MACD_signal = iMACD(g_symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
    // double MACD_hist = iMACD(g_symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE, MODE_HIST, 0); // Uncomment if needed
    
    // Calculate Bollinger Bands
    double BB_upper = iBands(g_symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 0);
    double BB_middle = iBands(g_symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN, 0);
    double BB_lower = iBands(g_symbol, g_timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 0);
    
    // Retrieve Price Data
    string priceData = getOHLCV(g_symbol, g_timeframe, TimeCurrent());
    string signals = getTradingSignals(g_symbol, g_timeframe);
    
    // Check if priceData is valid
    if(StringLen(priceData) == 0)
    {
        Print("Invalid price data. Skipping update.");
        return;
    }
    
    // Calculate additional indicators
    double ATR = iATR(g_symbol, g_timeframe, 14, 0);  // 14-period ATR
    double SAR = iSAR(g_symbol, g_timeframe, 0.02, 0.2, 0);  // Parabolic SAR
    double VWAP = calculateVWAP();  // You'll need to implement this
    
    
    // Calculate Fibonacci levels
    double high = High[iHighest(g_symbol, g_timeframe, MODE_HIGH, 20, 0)];
    double low = Low[iLowest(g_symbol, g_timeframe, MODE_LOW, 20, 0)];
    
    double fib_236 = high - ((high - low) * 0.236);
    double fib_382 = high - ((high - low) * 0.382);
    double fib_500 = high - ((high - low) * 0.500);
    double fib_618 = high - ((high - low) * 0.618);
    double fib_786 = high - ((high - low) * 0.786);
        
    // Check if all indicators have valid values
    if(MA_20 == EMPTY_VALUE || MA_50 == EMPTY_VALUE || RSI_14 == EMPTY_VALUE ||
       MACD_main == EMPTY_VALUE || MACD_signal == EMPTY_VALUE ||
       BB_upper == EMPTY_VALUE || BB_middle == EMPTY_VALUE || BB_lower == EMPTY_VALUE)
    {
        Print("One or more indicators returned EMPTY_VALUE. Skipping update.");
        return;
    }
    
    // Prepare TA Indicators JSON
    string taIndicators = StringFormat(
        "\"MA_20\":%.5f,\"MA_50\":%.5f,\"MA_200\":%.5f,\"RSI_14\":%.2f,\"MACD\":%.5f,\"MACD_signal\":%.5f,\"BB_upper\":%.5f,\"BB_middle\":%.5f,\"BB_lower\":%.5f,\"ATR\":%.5f,\"SAR\":%.5f,\"VWAP\":%.5f,\"FIB_236\":%.5f,\"FIB_382\":%.5f,\"FIB_500\":%.5f,\"FIB_618\":%.5f,\"FIB_786\":%.5f,\"FIB_HIGH\":%.5f,\"FIB_LOW\":%.5f",
        MA_20,
        MA_50,
        MA_200,
        RSI_14,
        MACD_main,
        MACD_signal,
        BB_upper,
        BB_middle,
        BB_lower,
        ATR,
        SAR,
        VWAP,
        fib_236, fib_382, fib_500, fib_618, fib_786,
        high, low
    );
    
    // Modify the JSON message to include new indicators
    //string taIndicators = StringFormat(
     //   "\"MA_20\":%.5f,\"MA_50\":%.5f,\"RSI_14\":%.2f,\"MACD\":%.5f,\"MACD_signal\":%.5f," 
     //   "\"BB_upper\":%.5f,\"BB_middle\":%.5f,\"BB_lower\":%.5f,"
     //   "\"ATR\":%.5f,\"SAR\":%.5f,\"VWAP\":%.5f",
     //   ma20, ma50, rsi, macd, macdSignal,
     //   bbUpper, bbMiddle, bbLower,
     //   atr, sar, vwap
   // );
    
    // Construct the JSON message
    string message = StringFormat(
        "{\"type\":\"real_time_update\",\"symbol\":\"%s\",\"timeframe\":%d,\"market_open\":%s,\"price_data\":{%s},\"signals\":%s,\"ta_indicators\":{%s}}",
        g_symbol,
        g_timeframe,
        isMarketOpen ? "true" : "false",  // Add market_open status
        priceData,
        signals,
        taIndicators
    );
    
    // Send the message via ZeroMQ PUB socket
    ZmqMsg updateMsg(message);
    if(!pubSocket.send(updateMsg))
    {
        Print("Error: Failed to send real-time update.");
    }
    else
    {
        Print("Sent real-time update: ", message);
    }
}

//+------------------------------------------------------------------+
//| Function to send test messages (optional, for debugging)         |
//+------------------------------------------------------------------+
void sendTestMessage()
{
    string message = "{\"type\":\"test_message\",\"content\":\"Hello from MT4!\"}";
    ZmqMsg testMsg(message);
    if(!pubSocket.send(testMsg))
    {
        Print("Error: Failed to send test message.");
    }
    else
    {
        Print("Sent test message: ", message);
    }
}
