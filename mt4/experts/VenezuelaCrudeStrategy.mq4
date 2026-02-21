//+------------------------------------------------------------------+
//|                                    VenezuelaCrudeStrategy.mq4    |
//|                        Venezuela Crude Oil Spike & Fade Orders   |
//|                                   Copyright 2026, RiseTrader     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, RiseTrader"
#property link      "https://risetrader.com"
#property version   "1.00"
#property strict

// ============================================================================
// STRATEGY CONFIGURATION - Venezuela Maduro Capture Play
// ============================================================================
// Market Context:
// - US captured Maduro on Jan 3, 2026
// - Venezuela has 303B barrels (world's largest reserves)
// - Expected gap up 5-8% on Sunday open
// - But structural oversupply (3.8M bpd) will push prices lower medium-term
// ============================================================================

#define MAGIC_NUMBER 20260104  // Strategy identifier

// Account settings
input double MaxRiskPercent = 2.0;        // Max risk per trade %
input double AccountBalance = 10000.0;    // Account balance for position sizing

// Symbol settings
input string TradeSymbol = "CrudeOIL";    // Symbol to trade

// Order expiration
input int SpikeDaysValid = 1;             // Days valid for spike orders
input int FadeDaysValid = 6;              // Days valid for fade orders
input int BreakdownDaysValid = 11;        // Days valid for breakdown orders
input int TrendDaysValid = 27;            // Days valid for trend orders

// ============================================================================
// PENDING ORDER DEFINITIONS
// ============================================================================

struct PendingOrder {
   string id;
   string phase;
   int type;           // OP_BUYSTOP=4, OP_SELLSTOP=5, OP_BUYLIMIT=2, OP_SELLLIMIT=3
   double entry;
   double sl;
   double tp;
   double lots;
   int daysValid;
   string comment;
};

// ============================================================================
// GLOBAL VARIABLES
// ============================================================================

PendingOrder orders[];
int ordersCount = 0;
bool ordersPlaced = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("===========================================");
   Print("VENEZUELA CRUDE STRATEGY - INITIALIZING");
   Print("===========================================");
   
   // Initialize order array
   InitializeOrders();
   
   Print("Strategy loaded with ", ordersCount, " pending orders");
   Print("Total risk: $", CalculateTotalRisk());
   Print("===========================================");
   
   // Display order summary
   DisplayOrderSummary();
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Initialize all pending orders                                      |
//+------------------------------------------------------------------+
void InitializeOrders()
{
   ArrayResize(orders, 8);
   ordersCount = 8;
   
   // PHASE 1: CATCH THE SPIKE (BUY_STOP orders)
   // These trigger if market gaps up and momentum continues
   
   // SPIKE_LONG_1
   orders[0].id = "SPIKE_LONG_1";
   orders[0].phase = "CATCH_SPIKE";
   orders[0].type = OP_BUYSTOP;
   orders[0].entry = 58.50;
   orders[0].sl = 57.00;
   orders[0].tp = 61.50;
   orders[0].lots = 0.50;
   orders[0].daysValid = SpikeDaysValid;
   orders[0].comment = "Catch gap momentum";
   
   // SPIKE_LONG_2
   orders[1].id = "SPIKE_LONG_2";
   orders[1].phase = "CATCH_SPIKE";
   orders[1].type = OP_BUYSTOP;
   orders[1].entry = 59.00;
   orders[1].sl = 57.50;
   orders[1].tp = 62.00;
   orders[1].lots = 0.30;
   orders[1].daysValid = SpikeDaysValid;
   orders[1].comment = "Secondary spike entry";
   
   // PHASE 2: FADE THE RALLY (SELL_LIMIT orders)
   // These trigger when price spikes to resistance levels
   
   // FADE_SHORT_1
   orders[2].id = "FADE_SHORT_1";
   orders[2].phase = "FADE_RALLY";
   orders[2].type = OP_SELLLIMIT;
   orders[2].entry = 60.50;
   orders[2].sl = 62.50;
   orders[2].tp = 57.00;
   orders[2].lots = 0.75;
   orders[2].daysValid = FadeDaysValid;
   orders[2].comment = "Primary fade at R1";
   
   // FADE_SHORT_2
   orders[3].id = "FADE_SHORT_2";
   orders[3].phase = "FADE_RALLY";
   orders[3].type = OP_SELLLIMIT;
   orders[3].entry = 61.50;
   orders[3].sl = 63.50;
   orders[3].tp = 56.50;
   orders[3].lots = 0.75;
   orders[3].daysValid = FadeDaysValid;
   orders[3].comment = "Secondary fade at R2";
   
   // FADE_SHORT_3
   orders[4].id = "FADE_SHORT_3";
   orders[4].phase = "FADE_RALLY";
   orders[4].type = OP_SELLLIMIT;
   orders[4].entry = 62.50;
   orders[4].sl = 64.00;
   orders[4].tp = 57.50;
   orders[4].lots = 0.50;
   orders[4].daysValid = FadeDaysValid;
   orders[4].comment = "Top of range fade";
   
   // PHASE 3: BREAKDOWN TRADES (SELL_STOP orders)
   // These trigger if market doesn't spike and breaks down
   
   // BREAKDOWN_SHORT_1
   orders[5].id = "BREAKDOWN_SHORT_1";
   orders[5].phase = "BREAKDOWN";
   orders[5].type = OP_SELLSTOP;
   orders[5].entry = 56.50;
   orders[5].sl = 58.50;
   orders[5].tp = 53.00;
   orders[5].lots = 1.00;
   orders[5].daysValid = BreakdownDaysValid;
   orders[5].comment = "Catch breakdown";
   
   // BREAKDOWN_SHORT_2
   orders[6].id = "BREAKDOWN_SHORT_2";
   orders[6].phase = "BREAKDOWN";
   orders[6].type = OP_SELLSTOP;
   orders[6].entry = 55.00;
   orders[6].sl = 57.00;
   orders[6].tp = 51.50;
   orders[6].lots = 0.75;
   orders[6].daysValid = BreakdownDaysValid;
   orders[6].comment = "Breakdown to Goldman target";
   
   // PHASE 4: MEDIUM-TERM POSITION (SELL_LIMIT)
   // Core short position after volatility settles
   
   // MEDIUM_TERM_SHORT
   orders[7].id = "MEDIUM_TERM_SHORT";
   orders[7].phase = "TREND_FOLLOW";
   orders[7].type = OP_SELLLIMIT;
   orders[7].entry = 59.00;
   orders[7].sl = 62.00;
   orders[7].tp = 52.00;
   orders[7].lots = 1.50;
   orders[7].daysValid = TrendDaysValid;
   orders[7].comment = "Core medium-term short";
}

//+------------------------------------------------------------------+
//| Display order summary                                              |
//+------------------------------------------------------------------+
void DisplayOrderSummary()
{
   Print("");
   Print("╔══════════════════════════════════════════════════════════╗");
   Print("║           PENDING ORDERS SUMMARY                         ║");
   Print("╠══════════════════════════════════════════════════════════╣");
   
   double totalRisk = 0;
   double totalLots = 0;
   
   for(int i = 0; i < ordersCount; i++)
   {
      double risk = MathAbs(orders[i].entry - orders[i].sl) * 100 * orders[i].lots;
      totalRisk += risk;
      totalLots += orders[i].lots;
      
      string typeStr = GetOrderTypeString(orders[i].type);
      Print(StringFormat("║ %s: %s @ $%.2f | SL: $%.2f | Risk: $%.0f",
            orders[i].id, typeStr, orders[i].entry, orders[i].sl, risk));
   }
   
   Print("╠══════════════════════════════════════════════════════════╣");
   Print(StringFormat("║ Total Orders: %d | Total Lots: %.2f | Total Risk: $%.0f", 
         ordersCount, totalLots, totalRisk));
   Print("╚══════════════════════════════════════════════════════════╝");
   Print("");
}

//+------------------------------------------------------------------+
//| Calculate total risk                                               |
//+------------------------------------------------------------------+
double CalculateTotalRisk()
{
   double totalRisk = 0;
   for(int i = 0; i < ordersCount; i++)
   {
      totalRisk += MathAbs(orders[i].entry - orders[i].sl) * 100 * orders[i].lots;
   }
   return totalRisk;
}

//+------------------------------------------------------------------+
//| Get order type as string                                           |
//+------------------------------------------------------------------+
string GetOrderTypeString(int type)
{
   switch(type)
   {
      case OP_BUYSTOP: return "BUY_STOP";
      case OP_SELLSTOP: return "SELL_STOP";
      case OP_BUYLIMIT: return "BUY_LIMIT";
      case OP_SELLLIMIT: return "SELL_LIMIT";
      default: return "UNKNOWN";
   }
}

//+------------------------------------------------------------------+
//| Place all pending orders                                           |
//+------------------------------------------------------------------+
void PlaceAllOrders()
{
   if(ordersPlaced)
   {
      Print("Orders already placed!");
      return;
   }
   
   Print("===========================================");
   Print("PLACING ALL PENDING ORDERS...");
   Print("===========================================");
   
   int successCount = 0;
   int failCount = 0;
   
   for(int i = 0; i < ordersCount; i++)
   {
      int ticket = PlacePendingOrder(orders[i]);
      
      if(ticket > 0)
      {
         Print("✅ ", orders[i].id, " placed successfully. Ticket: ", ticket);
         successCount++;
      }
      else
      {
         Print("❌ ", orders[i].id, " FAILED! Error: ", GetLastError());
         failCount++;
      }
      
      Sleep(500);  // Prevent rate limiting
   }
   
   Print("===========================================");
   Print("RESULTS: ", successCount, " placed, ", failCount, " failed");
   Print("===========================================");
   
   if(failCount == 0)
   {
      ordersPlaced = true;
   }
}

//+------------------------------------------------------------------+
//| Place single pending order                                         |
//+------------------------------------------------------------------+
int PlacePendingOrder(PendingOrder& order)
{
   // Calculate expiration time
   datetime expiration = TimeCurrent() + order.daysValid * 86400;
   
   // Normalize prices
   double entry = NormalizeDouble(order.entry, Digits);
   double sl = NormalizeDouble(order.sl, Digits);
   double tp = NormalizeDouble(order.tp, Digits);
   
   // Place order
   int ticket = OrderSend(
      TradeSymbol,           // Symbol
      order.type,            // Order type
      order.lots,            // Lots
      entry,                 // Price
      3,                     // Slippage
      sl,                    // Stop loss
      tp,                    // Take profit
      order.comment,         // Comment
      MAGIC_NUMBER,          // Magic number
      expiration,            // Expiration
      order.type == OP_BUYSTOP || order.type == OP_BUYLIMIT ? clrGreen : clrRed
   );
   
   return ticket;
}

//+------------------------------------------------------------------+
//| Cancel orders by phase                                             |
//+------------------------------------------------------------------+
void CancelOrdersByPhase(string phase)
{
   Print("Cancelling all ", phase, " orders...");
   
   int cancelled = 0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS))
      {
         if(OrderMagicNumber() == MAGIC_NUMBER)
         {
            string comment = OrderComment();
            
            // Check if order belongs to this phase
            for(int j = 0; j < ordersCount; j++)
            {
               if(orders[j].phase == phase && StringFind(comment, orders[j].comment) >= 0)
               {
                  if(OrderDelete(OrderTicket()))
                  {
                     Print("Cancelled: ", orders[j].id);
                     cancelled++;
                  }
               }
            }
         }
      }
   }
   
   Print("Cancelled ", cancelled, " orders for phase: ", phase);
}

//+------------------------------------------------------------------+
//| Cancel all strategy orders                                         |
//+------------------------------------------------------------------+
void CancelAllOrders()
{
   Print("Cancelling all Venezuela strategy orders...");
   
   int cancelled = 0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS))
      {
         if(OrderMagicNumber() == MAGIC_NUMBER)
         {
            if(OrderDelete(OrderTicket()))
            {
               cancelled++;
            }
         }
      }
   }
   
   Print("Cancelled ", cancelled, " orders");
   ordersPlaced = false;
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   // Strategy monitoring logic can be added here
   // For example: auto-cancel spike orders if muted open detected
}

//+------------------------------------------------------------------+
//| Chart event handler - Button clicks                                |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long& lparam, const double& dparam, const string& sparam)
{
   if(id == CHARTEVENT_KEYDOWN)
   {
      // P = Place all orders
      if(lparam == 'P')
      {
         PlaceAllOrders();
      }
      // C = Cancel all orders
      else if(lparam == 'C')
      {
         CancelAllOrders();
      }
      // 1 = Cancel CATCH_SPIKE phase
      else if(lparam == '1')
      {
         CancelOrdersByPhase("CATCH_SPIKE");
      }
      // 2 = Cancel FADE_RALLY phase
      else if(lparam == '2')
      {
         CancelOrdersByPhase("FADE_RALLY");
      }
      // 3 = Cancel BREAKDOWN phase
      else if(lparam == '3')
      {
         CancelOrdersByPhase("BREAKDOWN");
      }
   }
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("Venezuela Crude Strategy EA deinitialized");
}

//+------------------------------------------------------------------+
