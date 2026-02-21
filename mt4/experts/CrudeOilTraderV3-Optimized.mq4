//+------------------------------------------------------------------+
//|                                   CrudeOILTraderV3-Optimized.mq4 |
//|                                                             Slim |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Slim"
#property link      "https://www.mql5.com"
#property version   "1.02"
#property strict

// Input Parameters - Core Strategy
extern double RiskPercent = 1.0;          // Risk per trade (%)
extern int ATRPeriod = 10;                // ATR Period
extern double ATRMultiplier = 2.0;        // ATR Multiplier for Stop Loss
extern int EMAPeriod1 = 8;                // Fast EMA
extern int EMAPeriod2 = 29;               // Slow EMA
extern int RSIPeriod = 10;                // RSI Period
extern int RSIOverbought = 68;            // RSI Overbought Level
extern int RSIOversold = 32;              // RSI Oversold Level
extern int CCIPeriod = 20;                // CCI Period
extern int CCIOverBought = 100;           // CCI Overbought Level
extern int CCIOverSold = -80;            // CCI Oversold Level
extern bool UseCCIFilter = true;          // Use CCI as additional filter
extern bool UseStrictFilter = false;      // Require both RSI and CCI confirmation
// Core Strategy Parameters (add these with the other extern parameters)
extern int MovingPeriod = 20;         // Moving Average Period for closing trades
extern int MovingShift = 0;           // Moving Average Shift
extern int MACloseMethod = MODE_SMA;  // MA Method (0=SMA, 1=EMA, 2=SMMA, 3=LWMA)


// Time Filter Parameters
extern bool UseTimeFilter = true;         // Enable time filter
extern int TradingStartHour = 8;          // Start hour (GMT)
extern int TradingEndHour = 20;           // End hour (GMT)
extern bool AvoidNewsTime = true;         // Avoid trading around news times
extern int NewsBufferMinutes = 30;        // Minutes to avoid trading before/after typical news times
extern bool AvoidRollover = true;         // Avoid trading during rollover
extern int RolloverStartHour = 21;        // Rollover period start hour (GMT)
extern int RolloverEndHour = 22;          // Rollover period end hour (GMT)

// Trailing Stop Parameters
extern bool UseTrailingStop = false;       // Enable trailing stop - Optimized
extern bool UseDynamicTrailing = false;    // Use momentum-based dynamic trailing - Optimized
extern double TrailingStopMultiplier = 1.5; // Multiplier for trailing stop distance
extern int MomentumPeriod = 10;           // Period for momentum calculation
extern double MinimumDistance = 20;       // Minimum trailing stop distance in points

// Risk Management
extern int MaxSpread = 50;                // Maximum allowed spread in points
extern int MagicNumber = 20240430;        // Unique identifier for this EA
extern double VolatilityThreshold = 2.0;  // Maximum allowed volatility multiplier
extern double MinMarginLevel = 100.0;     // Minimum required margin level (%)
extern bool CloseOnlyInProfit = true;     // Only close trades when in profit - Optimized
extern double MinProfitClose = 0.0;       // Minimum profit to allow closure (in points)


// Global Variables
double g_stopLoss, g_takeProfit;
datetime g_lastTrailingCheck = 0;
double g_initialStopLoss = 0;

//Exit conditions
extern bool UseMAExit = true;        // Use MA crossover exit
extern bool UsePatternExit = true;   // Use pattern-based exit
extern bool RequireBothExits = false; // Require both conditions for exit


//+------------------------------------------------------------------+
//| Add these to the existing input parameters section                 |
//+------------------------------------------------------------------+
//extern double MinMarginLevel = 200.0;     // Minimum required margin level (%)
//extern bool CloseOnlyInProfit = true;     // Only close trades when in profit
//extern double MinProfitClose = 0.0;       // Minimum profit to allow closure (in points)

// Position Sizing - Optimized
extern double Lots = 0.2;                 // Fixed lot size - Optimized
extern double MaximumRisk = 0.17;         // Maximum risk per trade - Optimized
extern double DecreaseFactor = 3;         // Decrease factor for consecutive losses - Optimized

//+------------------------------------------------------------------+
//| Check margin level - Fixed                                        |
//+------------------------------------------------------------------+
bool IsMarginSafe()
  {
   double margin = AccountMargin();
   double equity = AccountEquity();
   
   // Protect against zero margin
   if(margin == 0) return true;  // No positions open
   
   // Calculate margin level with protection
   double marginLevel = equity / margin * 100;
   
   if(marginLevel < MinMarginLevel * 1.2)  // Warning at 120% of minimum
     {
      Print("Warning: Margin level (", DoubleToStr(marginLevel, 2),
            "%) approaching minimum threshold (", MinMarginLevel, "%)");
     }
   
   return (marginLevel >= MinMarginLevel);
  }


//+------------------------------------------------------------------+
//| Check if trade can be closed based on profit condition            |
//+------------------------------------------------------------------+
bool CanClosePosition(int ticket)
  {
   if(!CloseOnlyInProfit) return true;  // If feature is disabled, allow closing
     
   double profitPoints = 0.0;  // Initialize the variable
   
   if(OrderSelect(ticket, SELECT_BY_TICKET))
     {      
      if(OrderType() == OP_BUY)
        {
         profitPoints = Bid - OrderOpenPrice();
        }
      else if(OrderType() == OP_SELL)
        {
         profitPoints = OrderOpenPrice() - Ask;
        }
     
      // Convert to points
      profitPoints = NormalizeDouble(profitPoints / Point, 0);
     
      // Check if profit exceeds minimum required
      if(profitPoints > MinProfitClose)
         return true;
     }
   
   return false;
  }


//+------------------------------------------------------------------+
//| Check if current time is within allowed trading hours              |
//+------------------------------------------------------------------+
bool IsTimeToTrade()  // Renamed from IsTradeAllowed
  {
   if(!UseTimeFilter) return true;
   
   datetime currentTime = TimeCurrent();
   int currentHour = TimeHour(currentTime);
   int currentMinute = TimeMinute(currentTime);
   
   // Check regular trading hours
   if(currentHour < TradingStartHour || currentHour >= TradingEndHour)
      return false;
     
   // Check rollover period
   if(AvoidRollover)
     {
      if(currentHour >= RolloverStartHour && currentHour < RolloverEndHour)
         return false;
     }
   
   // Check news times (common crude oil news times)
   if(AvoidNewsTime)
     {
      // EIA Crude Oil Inventories (Wednesday 10:30 EST / 14:30 GMT)
      if(TimeDayOfWeek(currentTime) == 3)  // Wednesday
        {
         if(currentHour == 14 && currentMinute >= 30-NewsBufferMinutes)
            return false;
         if(currentHour == 15 && currentMinute <= NewsBufferMinutes)
            return false;
        }
     }
   
   return true;
  }

//+------------------------------------------------------------------+
//| Check if current volatility is acceptable                          |
//+------------------------------------------------------------------+
bool IsVolatilityAcceptable()
  {
   double currentATR = iATR(Symbol(), 0, ATRPeriod, 1);
   double averageATR = 0;
   
   // Calculate average ATR for comparison
   for(int i = 1; i <= ATRPeriod; i++)
     {
      averageATR += iATR(Symbol(), 0, ATRPeriod, i);
     }
   averageATR /= ATRPeriod;
   
   // Check if current volatility is within acceptable range
   if(currentATR > averageATR * VolatilityThreshold)
      return false;
     
   return true;
  }

//+------------------------------------------------------------------+
//| Calculate trailing stop - Fixed                                    |
//+------------------------------------------------------------------+
double CalculateTrailingStop(int type)
  {
   // Protect against zero initial stop loss
   if(g_initialStopLoss <= 0)
     {
      Print("Warning: Invalid initial stop loss. Using ATR-based stop.");
      g_initialStopLoss = iATR(Symbol(), 0, ATRPeriod, 1) * ATRMultiplier;
     }
   
   double momentum = iMomentum(Symbol(), 0, MomentumPeriod, PRICE_CLOSE, 1);
   double baseDistance = g_initialStopLoss * TrailingStopMultiplier;
   double trailingDistance;
   
   // Protect against zero momentum
   if(momentum == 0) momentum = 100;
   
   // Adjust trailing distance based on momentum with protection
   if(type == OP_BUY)
     {
      if(momentum > 100)
         trailingDistance = baseDistance * MathMax(0.1, (1 - (momentum-100)/200));
      else
         trailingDistance = baseDistance * MathMax(0.1, (1 + (100-momentum)/100));
     }
   else  // OP_SELL
     {
      if(momentum < 100)
         trailingDistance = baseDistance * MathMax(0.1, (1 - (100-momentum)/200));
      else
         trailingDistance = baseDistance * MathMax(0.1, (1 + (momentum-100)/100));
     }
   
   // Ensure minimum distance is maintained
   return MathMax(trailingDistance, MinimumDistance * Point);
  }
 
//+------------------------------------------------------------------+
//| Modified ManageTrailingStop function with profit check            |
//+------------------------------------------------------------------+
void ManageTrailingStop()
  {
   if(!UseTrailingStop || OrdersTotal() == 0) return;
   
   for(int i = 0; i < OrdersTotal(); i++)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
           {
            // Check if we can close this position
            if(!CanClosePosition(OrderTicket()))
              {
               Print("Trade #", OrderTicket(), " is in loss - holding position");
               continue;
              }
           
            double newStopLoss;
            bool modify = false;
           
            if(UseDynamicTrailing)
               g_stopLoss = CalculateTrailingStop(OrderType());
            else
               g_stopLoss = g_initialStopLoss * TrailingStopMultiplier;
           
            if(OrderType() == OP_BUY)
              {
               newStopLoss = Bid - g_stopLoss;
               // Only move stop loss up, never down
               if(newStopLoss > OrderStopLoss() + Point)
                  modify = true;
              }
            else if(OrderType() == OP_SELL)
              {
               newStopLoss = Ask + g_stopLoss;
               // Only move stop loss down, never up
               if(newStopLoss < OrderStopLoss() - Point)
                  modify = true;
              }
           
            if(modify)
              {
               bool result = OrderModify(OrderTicket(), OrderOpenPrice(), newStopLoss,
                                       OrderTakeProfit(), 0, clrBlue);
               if(!result)
                 {
                  int error = GetLastError();
                  Print("OrderModify error: ", GetErrorDescription(error));
                 }
              }
           }
        }
     }
  }


//+------------------------------------------------------------------+
//| Calculate position size based on risk percentage - Fixed           |
//+------------------------------------------------------------------+
double CalculatePositionSize(double stopLossPoints)
  {
   // Protect against zero or negative stopLoss
   if(stopLossPoints <= 0)
     {
      Print("Warning: Invalid stop loss points (", stopLossPoints, "). Using minimum stop of 10 points");
      stopLossPoints = 10;
     }
   
   double riskAmount = AccountBalance() * (RiskPercent / 100);
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   
   // Protect against zero tickValue
   if(tickValue == 0)
     {
      Print("Error: Tick value is zero. Using minimum lot size.");
      return MarketInfo(Symbol(), MODE_MINLOT);
     }
   
   double lotSize = NormalizeDouble(riskAmount / (stopLossPoints * tickValue), 2);
   
   // Ensure lot size is within allowed range
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   
   // Additional safety check for invalid lot sizes
   if(lotSize <= 0 || !MathIsValidNumber(lotSize))
     {
      Print("Warning: Invalid lot size calculation. Using minimum lot size.");
      return minLot;
     }
   
   return MathMin(MathMax(lotSize, minLot), maxLot);
  }


//+------------------------------------------------------------------+
//| Check if we can trade                                             |
//+------------------------------------------------------------------+
//bool CanTrade()
//  {
//   if(!IsTimeToTrade()) return false;
//   if(OrdersTotal() > 0) return false;
//   if(MarketInfo(Symbol(), MODE_SPREAD) > MaxSpread) return false;
//   return true;
//  }

//+------------------------------------------------------------------+
//| Modified CanTrade function with margin check                      |
//+------------------------------------------------------------------+
bool CanTrade()
  {
   if(!IsTimeToTrade()) return false;
   if(!IsTradeAllowed()) return false;
   if(!IsMarginSafe()) return false;
   if(OrdersTotal() > 0) return false;
   if(MarketInfo(Symbol(), MODE_SPREAD) > MaxSpread) return false;
   return true;
  }

//+------------------------------------------------------------------+
//| Check CCI conditions                                              |
//+------------------------------------------------------------------+
int CheckCCISignal()
  {
   double cci = iCCI(Symbol(), 0, CCIPeriod, PRICE_TYPICAL, 1);
   
   if(cci < CCIOverSold) return OP_BUY;
   if(cci > CCIOverBought) return OP_SELL;
   
   return -1;
  }

//+------------------------------------------------------------------+
//| Check RSI conditions                                              |
//+------------------------------------------------------------------+
int CheckRSISignal()
  {
   double rsi = iRSI(Symbol(), 0, RSIPeriod, PRICE_CLOSE, 1);
   
   if(rsi < RSIOversold) return OP_BUY;
   if(rsi > RSIOverbought) return OP_SELL;
   
   return -1;
  }
 
//+------------------------------------------------------------------+
//| Optimized signal generation with multiple timeframe confirmation   |
//+------------------------------------------------------------------+
int GetSignal()
  {
   // Multiple timeframe analysis
   double fastEMA_M1 = iMA(Symbol(), PERIOD_M1, EMAPeriod1, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slowEMA_M1 = iMA(Symbol(), PERIOD_M1, EMAPeriod2, 0, MODE_EMA, PRICE_CLOSE, 1);
   
   double fastEMA_M5 = iMA(Symbol(), PERIOD_M5, EMAPeriod1, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slowEMA_M5 = iMA(Symbol(), PERIOD_M5, EMAPeriod2, 0, MODE_EMA, PRICE_CLOSE, 1);
   
   // Get ATR for volatility-based stop loss
   double atr = iATR(Symbol(), 0, ATRPeriod, 1);
   
   // RSI signals on multiple timeframes
   double rsi_M1 = iRSI(Symbol(), PERIOD_M1, RSIPeriod, PRICE_CLOSE, 1);
   double rsi_M5 = iRSI(Symbol(), PERIOD_M5, RSIPeriod, PRICE_CLOSE, 1);
   
   // CCI signals on multiple timeframes
   double cci_M1 = iCCI(Symbol(), PERIOD_M1, CCIPeriod, PRICE_TYPICAL, 1);
   double cci_M5 = iCCI(Symbol(), PERIOD_M5, CCIPeriod, PRICE_TYPICAL, 1);
   
   // Momentum confirmation
   double momentum = iMomentum(Symbol(), PERIOD_M1, MomentumPeriod, PRICE_CLOSE, 1);
   
   // Calculate stop loss and take profit distances
   g_stopLoss = atr * ATRMultiplier;
   g_takeProfit = g_stopLoss * 2.5;  // Increased risk:reward ratio to 1:2.5
   
   // Buy Signal Conditions
   bool buyEMA_M1 = fastEMA_M1 > slowEMA_M1;
   bool buyEMA_M5 = fastEMA_M5 > slowEMA_M5;
   bool buyRSI_M1 = rsi_M1 < RSIOversold;
   bool buyRSI_M5 = rsi_M5 < RSIOversold;
   bool buyCCI_M1 = cci_M1 < CCIOverSold;
   bool buyCCI_M5 = cci_M5 < CCIOverSold;
   bool buyMomentum = momentum > 99.5;
   
   // Sell Signal Conditions
   bool sellEMA_M1 = fastEMA_M1 < slowEMA_M1;
   bool sellEMA_M5 = fastEMA_M5 < slowEMA_M5;
   bool sellRSI_M1 = rsi_M1 > RSIOverbought;
   bool sellRSI_M5 = rsi_M5 > RSIOverbought;
   bool sellCCI_M1 = cci_M1 > CCIOverBought;
   bool sellCCI_M5 = cci_M5 > CCIOverBought;
   bool sellMomentum = momentum < 100.5;
   
   // Enhanced Buy Signal
   if(buyEMA_M1 && buyEMA_M5)  // EMA alignment on both timeframes
     {
      if(UseCCIFilter)
        {
         if(UseStrictFilter)
           {
            // Require both RSI and CCI confirmations on at least one timeframe
            if((buyRSI_M1 && buyCCI_M1) || (buyRSI_M5 && buyCCI_M5))
              {
               if(buyMomentum) return OP_BUY;
              }
           }
         else
           {
            // More flexible: require either RSI or CCI confirmation
            if((buyRSI_M1 || buyRSI_M5) || (buyCCI_M1 || buyCCI_M5))
              {
               if(buyMomentum) return OP_BUY;
              }
           }
        }
      else
        {
         // Without CCI filter, just check RSI
         if(buyRSI_M1 || buyRSI_M5)
           {
            if(buyMomentum) return OP_BUY;
           }
        }
     }
   
   // Enhanced Sell Signal
   if(sellEMA_M1 && sellEMA_M5)  // EMA alignment on both timeframes
     {
      if(UseCCIFilter)
        {
         if(UseStrictFilter)
           {
            // Require both RSI and CCI confirmations on at least one timeframe
            if((sellRSI_M1 && sellCCI_M1) || (sellRSI_M5 && sellCCI_M5))
              {
               if(sellMomentum) return OP_SELL;
              }
           }
         else
           {
            // More flexible: require either RSI or CCI confirmation
            if((sellRSI_M1 || sellRSI_M5) || (sellCCI_M1 || sellCCI_M5))
              {
               if(sellMomentum) return OP_SELL;
              }
           }
        }
      else
        {
         // Without CCI filter, just check RSI
         if(sellRSI_M1 || sellRSI_M5)
           {
            if(sellMomentum) return OP_SELL;
           }
        }
     }
   
   return -1;
  }
 
//+------------------------------------------------------------------+
//| Trade operation error handling                                     |
//+------------------------------------------------------------------+
string GetErrorDescription(int error_code)
  {
   switch(error_code)
     {
      case 0:   return "No error";
      case 1:   return "No error, trade conditions not changed";
      case 2:   return "Common error";
      case 3:   return "Invalid trade parameters";
      case 4:   return "Trade server is busy";
      case 5:   return "Old version of the client terminal";
      case 6:   return "No connection with trade server";
      case 7:   return "Not enough rights";
      case 8:   return "Too frequent requests";
      case 9:   return "Malfunctional trade operation";
      case 64:  return "Account disabled";
      case 65:  return "Invalid account";
      case 128: return "Trade timeout";
      case 129: return "Invalid price";
      case 130: return "Invalid stops";
      case 131: return "Invalid trade volume";
      case 132: return "Market is closed";
      case 133: return "Trade is disabled";
      case 134: return "Not enough money";
      case 135: return "Price changed";
      default:  return "Unknown error";
     }
  }

//+------------------------------------------------------------------+
//| Enhanced exit conditions                                           |
//+------------------------------------------------------------------+
bool ShouldClosePosition(int type, double ma, double open, double close)
  {
   if(type == OP_BUY)
     {
      // Exit long positions on bearish engulfing or strong reversal
      bool bearishEngulfing = close < open && close < ma;
      bool strongReversal = Close[1] < Close[2] && Close[2] < Close[3];
      return bearishEngulfing || strongReversal;
     }
   else if(type == OP_SELL)
     {
      // Exit short positions on bullish engulfing or strong reversal
      bool bullishEngulfing = close > open && close > ma;
      bool strongReversal = Close[1] > Close[2] && Close[2] > Close[3];
      return bullishEngulfing || strongReversal;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Modified CheckForClose function with complete error checking       |
//+------------------------------------------------------------------+
void CheckForClose()
  {
   double ma = iMA(NULL, 0, MovingPeriod, MovingShift, MODE_SMA, PRICE_CLOSE, 0);
   
   for(int i = 0; i < OrdersTotal(); i++)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
           {
            // Check if we can close this position
            if(!CanClosePosition(OrderTicket()))
              {
               Print("Trade #", OrderTicket(), " is in loss - holding position");
               continue;
              }
           
            bool shouldClose = false;
            double closePrice = 0;
           
            if(OrderType() == OP_BUY)
              {
               shouldClose = (Open[1] > ma && Close[1] < ma);
               closePrice = Bid;
              }
            else if(OrderType() == OP_SELL)
              {
               shouldClose = (Open[1] < ma && Close[1] > ma);
               closePrice = Ask;
              }
           
            if(shouldClose)
              {
               int ticket = OrderTicket();
               double lots = OrderLots();
               
               
               RefreshRates();  // Get latest prices before closing
               
               
               // Try to close the position
               bool result = OrderClose(ticket, lots, closePrice, 3, White);
               
               // Check if close operation was successful
               if(!result)
                 {
                  int error = GetLastError();
                  Print("Failed to close order #", ticket, ". Error: ", GetErrorDescription(error),
                        " (", error, "). Price: ", closePrice, ", Lots: ", lots);
                 
                  // Additional error handling based on specific error codes
                  switch(error)
                    {
                     case 129: // Invalid price
                        Print("Current Bid: ", Bid, " Ask: ", Ask, " Requested close price: ", closePrice);
                        break;
                     case 131: // Invalid volume
                        Print("Requested volume: ", lots, " may be invalid");
                        break;
                     case 138: // Requote
                        RefreshRates(); // Try to get new prices
                        break;
                     case 4: // Trade server is busy
                     case 6: // No connection with trade server
                     case 128: // Trade timeout
                        Sleep(3000); // Wait before next attempt
                        break;
                    }
                 }
               else
                 {
                  Print("Successfully closed order #", ticket, " at price ", closePrice,
                        " with profit: ", OrderProfit());
                 }
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Calculate optimal lot size                                       |
//+------------------------------------------------------------------+
double LotsOptimized()
  {
   double lot=Lots;
   int    orders=HistoryTotal();     // history orders total
   int    losses=0;                  // number of losses orders without a break
//--- select lot size
   lot=NormalizeDouble(AccountFreeMargin()*MaximumRisk/1000.0,1);
//--- calcuulate number of losses orders without a break
   if(DecreaseFactor>0)
     {
      for(int i=orders-1;i>=0;i--)
        {
         if(OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)==false)
           {
            Print("Error in history!");
            break;
           }
         if(OrderSymbol()!=Symbol() || OrderType()>OP_SELL)
            continue;
         //---
         if(OrderProfit()>0) break;
         if(OrderProfit()<0) losses++;
        }
      if(losses>1)
         lot=NormalizeDouble(lot-lot*losses/DecreaseFactor,1);
     }
//--- return lot size
   if(lot<0.1) lot=0.1;
   return(lot);
  }

//+------------------------------------------------------------------+
//| Modified OnTick function with enhanced checks                     |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Always check margin first
   if(!IsMarginSafe())
     {
      Print("Warning: Margin level below minimum threshold!");
      return;
     }
   
   // Check time-based filters
   if(!IsTimeToTrade() || !IsVolatilityAcceptable())
      return;
   
   // Manage existing positions
   if(OrdersTotal() > 0)
     {
      ManageTrailingStop();
      CheckForClose();  // Add this line
      return;
     }
   
   // Check for new trade opportunities
   if(!CanTrade()) return;
   
   int signal = GetSignal();
   if(signal == -1) return;
   
   double lots = CalculatePositionSize(g_stopLoss);
   double stopLossPrice, takeProfitPrice;
     
   int ticket = -1;
   
   if(signal == OP_BUY)
     {
      stopLossPrice = Bid - g_stopLoss;
      takeProfitPrice = Bid + g_takeProfit;
      g_initialStopLoss = g_stopLoss;
     
      ticket = OrderSend(Symbol(), OP_BUY, LotsOptimized(), Ask, 3, 0, 0, //lots, Ask, 3, stopLossPrice, takeProfitPrice, "CrudeOil
                "", MagicNumber, 0, clrGreen);            
           
      //res=OrderSend(Symbol(),OP_BUY,LotsOptimized(),Ask,3,0,0,"",MAGICMA,0,Blue);
     }
   else if(signal == OP_SELL)
     {
      stopLossPrice = Ask + g_stopLoss;
      takeProfitPrice = Ask - g_takeProfit;
      g_initialStopLoss = g_stopLoss;
     
      ticket = OrderSend(Symbol(), OP_SELL, LotsOptimized(), Bid, 3, 0, 0, //lots, Bid, 3, stopLossPrice, takeProfitPrice, "CrudeOil
                "", MagicNumber, 0, clrRed);
     }
  }

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Validate inputs
   if(RiskPercent <= 0 || RiskPercent > 5)
     {
      Print("Invalid Risk Percent. Must be between 0 and 5");
      return INIT_PARAMETERS_INCORRECT;
     }
   
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   // Cleanup if needed
  }