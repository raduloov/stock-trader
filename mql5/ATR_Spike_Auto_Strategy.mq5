//+------------------------------------------------------------------+
//| ATR Spike Auto Strategy (Session Only)                           |
//| Converted from PineScript v5                                     |
//|                                                                  |
//| BUY:  Fast EMA (20) crosses above Slow EMA (50)                 |
//| SELL: Fast EMA (20) crosses below Slow EMA (50)                 |
//| EXIT: Price moves ATR * 1.5 against position                    |
//+------------------------------------------------------------------+
#property copyright "Stock Trader Bot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

// ───── Inputs ─────
input int    FastEmaLen = 20;          // Fast EMA Length
input int    SlowEmaLen = 50;          // Slow EMA Length
input int    AtrLen     = 14;          // ATR Length
input double AtrMult    = 1.5;        // ATR Exit Multiplier
input double LotSize    = 0.01;       // Lot Size
input int    MagicNumber = 123456;    // Magic Number (unique ID for this EA)

// ───── Globals ─────
CTrade trade;
int handleFastEma;
int handleSlowEma;
int handleAtr;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);

    handleFastEma = iMA(_Symbol, PERIOD_CURRENT, FastEmaLen, 0, MODE_EMA, PRICE_CLOSE);
    handleSlowEma = iMA(_Symbol, PERIOD_CURRENT, SlowEmaLen, 0, MODE_EMA, PRICE_CLOSE);
    handleAtr     = iATR(_Symbol, PERIOD_CURRENT, AtrLen);

    if(handleFastEma == INVALID_HANDLE || handleSlowEma == INVALID_HANDLE || handleAtr == INVALID_HANDLE)
    {
        Print("Error creating indicator handles");
        return INIT_FAILED;
    }

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(handleFastEma);
    IndicatorRelease(handleSlowEma);
    IndicatorRelease(handleAtr);
}

//+------------------------------------------------------------------+
//| Get indicator value                                              |
//+------------------------------------------------------------------+
double GetIndicatorValue(int handle, int shift)
{
    double buffer[];
    ArraySetAsSeries(buffer, true);
    if(CopyBuffer(handle, 0, shift, 1, buffer) <= 0)
        return 0.0;
    return buffer[0];
}

//+------------------------------------------------------------------+
//| Check if we have an open position for this EA                    |
//+------------------------------------------------------------------+
int GetPositionType()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                return (int)PositionGetInteger(POSITION_TYPE);
            }
        }
    }
    return -1; // No position
}

//+------------------------------------------------------------------+
//| Get average entry price of current position                      |
//+------------------------------------------------------------------+
double GetPositionAvgPrice()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                return PositionGetDouble(POSITION_PRICE_OPEN);
            }
        }
    }
    return 0.0;
}

//+------------------------------------------------------------------+
//| Close all positions for this EA                                  |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                trade.PositionClose(ticket);
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    // Only run on new bar
    static datetime lastBar = 0;
    datetime currentBar = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(currentBar == lastBar)
        return;
    lastBar = currentBar;

    // ───── Get indicator values ─────
    // Current bar (index 1 = last closed bar, index 2 = bar before)
    double fastEmaCurr = GetIndicatorValue(handleFastEma, 1);
    double fastEmaPrev = GetIndicatorValue(handleFastEma, 2);
    double slowEmaCurr = GetIndicatorValue(handleSlowEma, 1);
    double slowEmaPrev = GetIndicatorValue(handleSlowEma, 2);
    double atrValue    = GetIndicatorValue(handleAtr, 1);
    double closePrice  = iClose(_Symbol, PERIOD_CURRENT, 1);

    if(fastEmaCurr == 0 || slowEmaCurr == 0 || atrValue == 0)
        return;

    // ───── Crossover / Crossunder detection ─────
    bool longCondition  = (fastEmaPrev <= slowEmaPrev) && (fastEmaCurr > slowEmaCurr);
    bool shortCondition = (fastEmaPrev >= slowEmaPrev) && (fastEmaCurr < slowEmaCurr);

    // ───── Current position state ─────
    int posType = GetPositionType();
    double avgPrice = GetPositionAvgPrice();

    // ───── Exit: price moves ATR * mult against position ─────
    bool exitLong  = (posType == POSITION_TYPE_BUY)  && (closePrice < avgPrice - atrValue * AtrMult);
    bool exitShort = (posType == POSITION_TYPE_SELL) && (closePrice > avgPrice + atrValue * AtrMult);

    if(exitLong || exitShort)
    {
        Print("ATR exit triggered | Close=", closePrice, " AvgPrice=", avgPrice, " ATR=", atrValue);
        CloseAllPositions();
        return;
    }

    // ───── Entry: Long ─────
    if(longCondition)
    {
        // Close any existing short first
        if(posType == POSITION_TYPE_SELL)
            CloseAllPositions();

        if(posType != POSITION_TYPE_BUY)
        {
            Print("BUY signal | FastEMA=", fastEmaCurr, " SlowEMA=", slowEmaCurr);
            trade.Buy(LotSize, _Symbol);
        }
    }

    // ───── Entry: Short ─────
    if(shortCondition)
    {
        // Close any existing long first
        if(posType == POSITION_TYPE_BUY)
            CloseAllPositions();

        if(posType != POSITION_TYPE_SELL)
        {
            Print("SELL signal | FastEMA=", fastEmaCurr, " SlowEMA=", slowEmaCurr);
            trade.Sell(LotSize, _Symbol);
        }
    }
}
//+------------------------------------------------------------------+
