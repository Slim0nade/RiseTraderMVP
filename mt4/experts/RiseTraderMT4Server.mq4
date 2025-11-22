//+------------------------------------------------------------------+
//|                                        RiseTraderMT4Server.mq4   |
//|                                    RiseTrader MT4 Integration    |
//|                            Server-side EA for ZMQ communication  |
//+------------------------------------------------------------------+
#property copyright "RiseTrader"
#property link      "https://github.com/risetrader"
#property version   "1.00"
#property strict

// Import ZMQ library (requires mql-zmq library installation)
// Download from: https://github.com/dingmaotu/mql-zmq
#include <Zmq/Zmq.mqh>

//--- Input Parameters
input string   ServerSecretKey = "";        // Server Secret Key (Z85, 40 chars)
input string   ServerPublicKey = "";        // Server Public Key (Z85, 40 chars)
input string   ClientPublicKey = "";        // Client Public Key (Z85, 40 chars)
input int      REP_PORT = 5555;             // REP socket port (commands)
input int      PUB_PORT = 5556;             // PUB socket port (streaming)
input int      MagicNumber = 100001;        // Magic number for this EA
input string   TradingSymbol = "CrudeOIL";  // Primary trading symbol
input bool     EnableEncryption = true;     // Enable CurveZMQ encryption
input bool     EnableLogging = true;        // Enable debug logging
input int      HeartbeatIntervalMs = 30000; // Heartbeat interval (30s)

//--- Global Variables
Context context;
Socket repSocket;     // REP socket for commands
Socket pubSocket;     // PUB socket for streaming
datetime lastHeartbeat = 0;
bool isInitialized = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("RiseTrader MT4 Server EA initializing...");
   Print("Magic Number: ", MagicNumber);
   Print("REP Port: ", REP_PORT);
   Print("PUB Port: ", PUB_PORT);
   Print("Symbol: ", TradingSymbol);
   Print("Encryption: ", EnableEncryption ? "ENABLED" : "DISABLED");

   // Validate encryption keys if encryption is enabled
   if(EnableEncryption)
   {
      if(StringLen(ServerSecretKey) != 40)
      {
         Print("ERROR: Server Secret Key must be 40 characters (Z85-encoded)");
         return(INIT_PARAMETERS_INCORRECT);
      }

      if(StringLen(ServerPublicKey) != 40)
      {
         Print("ERROR: Server Public Key must be 40 characters (Z85-encoded)");
         return(INIT_PARAMETERS_INCORRECT);
      }

      if(StringLen(ClientPublicKey) != 40)
      {
         Print("ERROR: Client Public Key must be 40 characters (Z85-encoded)");
         return(INIT_PARAMETERS_INCORRECT);
      }

      Print("Encryption keys validated");
   }

   // Initialize ZMQ context
   context = new Context();

   // Setup REP socket (for commands)
   if(!SetupRepSocket())
   {
      Print("ERROR: Failed to setup REP socket");
      return(INIT_FAILED);
   }

   // Setup PUB socket (for streaming)
   if(!SetupPubSocket())
   {
      Print("ERROR: Failed to setup PUB socket");
      return(INIT_FAILED);
   }

   isInitialized = true;
   Print("RiseTrader MT4 Server EA initialized successfully");

   // Send initial connection event
   PublishConnectionStatus("ACTIVE", "");

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("RiseTrader MT4 Server EA shutting down...");

   // Send disconnection event
   if(isInitialized)
   {
      PublishConnectionStatus("INACTIVE", "EA stopped");
   }

   // Close sockets
   if(CheckPointer(repSocket) == POINTER_DYNAMIC)
   {
      repSocket.disconnect(StringFormat("tcp://*:%d", REP_PORT));
      repSocket.unbind(StringFormat("tcp://*:%d", REP_PORT));
      delete repSocket;
   }

   if(CheckPointer(pubSocket) == POINTER_DYNAMIC)
   {
      pubSocket.disconnect(StringFormat("tcp://*:%d", PUB_PORT));
      pubSocket.unbind(StringFormat("tcp://*:%d", PUB_PORT));
      delete pubSocket;
   }

   // Destroy context
   if(CheckPointer(context) == POINTER_DYNAMIC)
   {
      delete context;
   }

   Print("RiseTrader MT4 Server EA shut down complete");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!isInitialized) return;

   // Process incoming commands (non-blocking)
   ProcessCommands();

   // Publish market tick data
   PublishMarketTick();

   // Send heartbeat periodically
   if(TimeCurrent() - lastHeartbeat >= HeartbeatIntervalMs / 1000)
   {
      PublishHeartbeat();
      lastHeartbeat = TimeCurrent();
   }

   // Check for position updates
   CheckPositionUpdates();
}

//+------------------------------------------------------------------+
//| Setup REP socket for commands                                     |
//+------------------------------------------------------------------+
bool SetupRepSocket()
{
   repSocket = context.socket(ZMQ_REP);

   if(CheckPointer(repSocket) != POINTER_DYNAMIC)
   {
      Print("ERROR: Failed to create REP socket");
      return false;
   }

   // Configure encryption
   if(EnableEncryption)
   {
      repSocket.setCurveServer(true);
      repSocket.setCurveSecretKey(ServerSecretKey);
   }

   // Bind socket
   string address = StringFormat("tcp://*:%d", REP_PORT);
   if(!repSocket.bind(address))
   {
      Print("ERROR: Failed to bind REP socket to ", address);
      return false;
   }

   // Set socket options
   repSocket.setReceiveTimeout(0);  // Non-blocking

   Print("REP socket bound to ", address);
   return true;
}

//+------------------------------------------------------------------+
//| Setup PUB socket for streaming                                    |
//+------------------------------------------------------------------+
bool SetupPubSocket()
{
   pubSocket = context.socket(ZMQ_PUB);

   if(CheckPointer(pubSocket) != POINTER_DYNAMIC)
   {
      Print("ERROR: Failed to create PUB socket");
      return false;
   }

   // Configure encryption
   if(EnableEncryption)
   {
      pubSocket.setCurveServer(true);
      pubSocket.setCurveSecretKey(ServerSecretKey);
   }

   // Bind socket
   string address = StringFormat("tcp://*:%d", PUB_PORT);
   if(!pubSocket.bind(address))
   {
      Print("ERROR: Failed to bind PUB socket to ", address);
      return false;
   }

   Print("PUB socket bound to ", address);
   return true;
}

//+------------------------------------------------------------------+
//| Process incoming commands from RiseTrader                         |
//+------------------------------------------------------------------+
void ProcessCommands()
{
   ZmqMsg request;

   // Non-blocking receive
   if(!repSocket.recv(request, true))
   {
      return;  // No messages waiting
   }

   string message = request.getData();

   if(EnableLogging)
   {
      Print("Received command: ", message);
   }

   // Parse JSON command
   string response = HandleCommand(message);

   // Send response
   ZmqMsg reply(response);
   repSocket.send(reply);

   if(EnableLogging)
   {
      Print("Sent response: ", response);
   }
}

//+------------------------------------------------------------------+
//| Handle command and generate response                              |
//+------------------------------------------------------------------+
string HandleCommand(string commandJson)
{
   // Parse command type from JSON
   // Simplified JSON parsing - production should use proper JSON library

   string response = "";

   if(StringFind(commandJson, "\"command\":\"create_instant_order\"") >= 0)
   {
      response = HandleCreateInstantOrder(commandJson);
   }
   else if(StringFind(commandJson, "\"command\":\"get_account_info\"") >= 0)
   {
      response = HandleGetAccountInfo(commandJson);
   }
   else if(StringFind(commandJson, "\"command\":\"get_open_positions\"") >= 0)
   {
      response = HandleGetOpenPositions(commandJson);
   }
   else if(StringFind(commandJson, "\"command\":\"close_position\"") >= 0)
   {
      response = HandleClosePosition(commandJson);
   }
   else if(StringFind(commandJson, "\"command\":\"test_connection\"") >= 0)
   {
      response = HandleTestConnection(commandJson);
   }
   else
   {
      response = ErrorResponse("Unknown command", 1000);
   }

   return response;
}

//+------------------------------------------------------------------+
//| Handle create instant order command                               |
//+------------------------------------------------------------------+
string HandleCreateInstantOrder(string commandJson)
{
   // Parse parameters (simplified - use proper JSON parser in production)
   string symbol = ExtractJsonString(commandJson, "symbol");
   string direction = ExtractJsonString(commandJson, "direction");
   double volume = ExtractJsonDouble(commandJson, "volume");
   double stopLoss = ExtractJsonDouble(commandJson, "stop_loss");
   double takePro fit = ExtractJsonDouble(commandJson, "take_profit");

   if(symbol == "") symbol = TradingSymbol;

   // Determine order type
   int orderType = (direction == "BUY") ? OP_BUY : OP_SELL;

   // Get current price
   double price = (orderType == OP_BUY) ? Ask : Bid;

   // Place order
   int ticket = OrderSend(
      symbol,
      orderType,
      volume,
      price,
      3,  // 3 pip slippage
      stopLoss,
      takeProfit,
      StringFormat("RiseTrader_%d", MagicNumber),
      MagicNumber,
      0,
      clrNone
   );

   if(ticket > 0)
   {
      // Success - publish order_confirmed event
      PublishOrderConfirmed(ticket, symbol, direction, volume, price);

      return SuccessResponse(ticket, price);
   }
   else
   {
      // Error
      int errorCode = GetLastError();
      string errorMsg = ErrorDescription(errorCode);

      return ErrorResponse(errorMsg, errorCode);
   }
}

//+------------------------------------------------------------------+
//| Handle get account info command                                   |
//+------------------------------------------------------------------+
string HandleGetAccountInfo(string commandJson)
{
   string response = StringFormat(
      "{\"success\":true,"
      "\"account_number\":%d,"
      "\"balance\":%.2f,"
      "\"equity\":%.2f,"
      "\"margin\":%.2f,"
      "\"free_margin\":%.2f,"
      "\"margin_level\":%.2f,"
      "\"leverage\":%d}",
      AccountNumber(),
      AccountBalance(),
      AccountEquity(),
      AccountMargin(),
      AccountFreeMargin(),
      AccountMargin() > 0 ? AccountEquity() / AccountMargin() * 100 : 999.99,
      AccountLeverage()
   );

   return response;
}

//+------------------------------------------------------------------+
//| Handle get open positions command                                 |
//+------------------------------------------------------------------+
string HandleGetOpenPositions(string commandJson)
{
   string positions = "[";
   bool first = true;

   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == MagicNumber)
         {
            if(!first) positions += ",";

            positions += StringFormat(
               "{\"ticket\":%d,"
               "\"symbol\":\"%s\","
               "\"direction\":\"%s\","
               "\"volume\":%.2f,"
               "\"open_price\":%.5f,"
               "\"current_price\":%.5f,"
               "\"unrealized_pnl\":%.2f,"
               "\"stop_loss\":%.5f,"
               "\"take_profit\":%.5f}",
               OrderTicket(),
               OrderSymbol(),
               (OrderType() == OP_BUY) ? "BUY" : "SELL",
               OrderLots(),
               OrderOpenPrice(),
               OrderClosePrice(),
               OrderProfit(),
               OrderStopLoss(),
               OrderTakeProfit()
            );

            first = false;
         }
      }
   }

   positions += "]";

   return StringFormat("{\"success\":true,\"positions\":%s}", positions);
}

//+------------------------------------------------------------------+
//| Handle close position command                                     |
//+------------------------------------------------------------------+
string HandleClosePosition(string commandJson)
{
   int ticket = ExtractJsonInt(commandJson, "ticket_number");

   if(OrderSelect(ticket, SELECT_BY_TICKET))
   {
      if(OrderMagicNumber() == MagicNumber)
      {
         bool result = OrderClose(
            OrderTicket(),
            OrderLots(),
            OrderClosePrice(),
            3,
            clrNone
         );

         if(result)
         {
            // Publish position_closed event
            PublishPositionClosed(ticket);

            return StringFormat("{\"success\":true,\"ticket\":%d}", ticket);
         }
      }
   }

   return ErrorResponse("Failed to close position", GetLastError());
}

//+------------------------------------------------------------------+
//| Handle test connection command                                    |
//+------------------------------------------------------------------+
string HandleTestConnection(string commandJson)
{
   return StringFormat(
      "{\"success\":true,"
      "\"message\":\"Connection OK\","
      "\"magic_number\":%d,"
      "\"symbol\":\"%s\","
      "\"server_time\":\"%s\"}",
      MagicNumber,
      TradingSymbol,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
}

//+------------------------------------------------------------------+
//| Publish market tick event                                         |
//+------------------------------------------------------------------+
void PublishMarketTick()
{
   string event = StringFormat(
      "{\"event_type\":\"market_tick\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{"
      "\"symbol\":\"%s\","
      "\"bid\":%.5f,"
      "\"ask\":%.5f\"}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      TradingSymbol,
      Bid,
      Ask
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);
}

//+------------------------------------------------------------------+
//| Publish order confirmed event                                     |
//+------------------------------------------------------------------+
void PublishOrderConfirmed(int ticket, string symbol, string direction, double volume, double price)
{
   string event = StringFormat(
      "{\"event_type\":\"order_confirmed\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{"
      "\"ticket_number\":%d,"
      "\"magic_number\":%d,"
      "\"symbol\":\"%s\","
      "\"direction\":\"%s\","
      "\"volume\":%.2f,"
      "\"execution_price\":%.5f}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      ticket,
      MagicNumber,
      symbol,
      direction,
      volume,
      price
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);

   Print("Published order_confirmed event for ticket ", ticket);
}

//+------------------------------------------------------------------+
//| Publish position closed event                                     |
//+------------------------------------------------------------------+
void PublishPositionClosed(int ticket)
{
   string event = StringFormat(
      "{\"event_type\":\"position_closed\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{\"ticket_number\":%d,\"magic_number\":%d}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      ticket,
      MagicNumber
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);
}

//+------------------------------------------------------------------+
//| Publish connection status event                                   |
//+------------------------------------------------------------------+
void PublishConnectionStatus(string status, string error)
{
   string event = StringFormat(
      "{\"event_type\":\"connection_status_changed\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{\"magic_number\":%d,\"status\":\"%s\",\"error_message\":\"%s\"}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      MagicNumber,
      status,
      error
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);
}

//+------------------------------------------------------------------+
//| Publish heartbeat                                                 |
//+------------------------------------------------------------------+
void PublishHeartbeat()
{
   string event = StringFormat(
      "{\"event_type\":\"heartbeat\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{\"magic_number\":%d}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      MagicNumber
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);
}

//+------------------------------------------------------------------+
//| Check for position updates                                        |
//+------------------------------------------------------------------+
void CheckPositionUpdates()
{
   // Check all open positions and publish updates if P&L changed
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == MagicNumber)
         {
            // Publish position update
            PublishPositionUpdate(
               OrderTicket(),
               OrderSymbol(),
               OrderType() == OP_BUY ? "BUY" : "SELL",
               OrderLots(),
               OrderOpenPrice(),
               OrderClosePrice(),
               OrderProfit()
            );
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Publish position update event                                     |
//+------------------------------------------------------------------+
void PublishPositionUpdate(int ticket, string symbol, string direction,
                          double volume, double openPrice, double currentPrice, double pnl)
{
   string event = StringFormat(
      "{\"event_type\":\"position_updated\","
      "\"version\":\"1.0.0\","
      "\"timestamp\":\"%s\","
      "\"data\":{"
      "\"ticket_number\":%d,"
      "\"magic_number\":%d,"
      "\"symbol\":\"%s\","
      "\"direction\":\"%s\","
      "\"volume\":%.2f,"
      "\"open_price\":%.5f,"
      "\"current_price\":%.5f,"
      "\"unrealized_pnl\":%.2f}}",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      ticket,
      MagicNumber,
      symbol,
      direction,
      volume,
      openPrice,
      currentPrice,
      pnl
   );

   ZmqMsg msg(event);
   pubSocket.send(msg);
}

//+------------------------------------------------------------------+
//| Helper: Success response                                          |
//+------------------------------------------------------------------+
string SuccessResponse(int ticket, double price)
{
   return StringFormat(
      "{\"success\":true,"
      "\"ticket_number\":%d,"
      "\"execution_price\":%.5f,"
      "\"execution_time\":\"%s\"}",
      ticket,
      price,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );
}

//+------------------------------------------------------------------+
//| Helper: Error response                                            |
//+------------------------------------------------------------------+
string ErrorResponse(string message, int code)
{
   return StringFormat(
      "{\"success\":false,"
      "\"error_code\":%d,"
      "\"error_message\":\"%s\"}",
      code,
      message
   );
}

//+------------------------------------------------------------------+
//| Helper: Extract string from JSON                                  |
//+------------------------------------------------------------------+
string ExtractJsonString(string json, string key)
{
   // Simplified JSON extraction - use proper parser in production
   int startPos = StringFind(json, "\"" + key + "\":\"");
   if(startPos < 0) return "";

   startPos += StringLen(key) + 4;
   int endPos = StringFind(json, "\"", startPos);

   if(endPos < 0) return "";

   return StringSubstr(json, startPos, endPos - startPos);
}

//+------------------------------------------------------------------+
//| Helper: Extract double from JSON                                  |
//+------------------------------------------------------------------+
double ExtractJsonDouble(string json, string key)
{
   int startPos = StringFind(json, "\"" + key + "\":");
   if(startPos < 0) return 0.0;

   startPos += StringLen(key) + 3;

   // Skip whitespace
   while(startPos < StringLen(json) && StringGetCharacter(json, startPos) == ' ')
      startPos++;

   int endPos = startPos;
   while(endPos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, endPos);
      if(ch == ',' || ch == '}' || ch == ' ') break;
      endPos++;
   }

   string value = StringSubstr(json, startPos, endPos - startPos);
   return StringToDouble(value);
}

//+------------------------------------------------------------------+
//| Helper: Extract int from JSON                                     |
//+------------------------------------------------------------------+
int ExtractJsonInt(string json, string key)
{
   return (int)ExtractJsonDouble(json, key);
}
//+------------------------------------------------------------------+
