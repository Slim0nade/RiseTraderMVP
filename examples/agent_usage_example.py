"""
RiseTrader Agent System - Usage Example

Demonstrates how to use the intelligent trading agents:
1. Analysis Layer: Technical, Fundamental, Sentiment analysis
2. Decision Layer: Position sizing, Stop-loss, Take-profit
3. Execution Layer: Trade execution, Position monitoring

This example shows the complete flow from analysis to execution.
"""

import asyncio
from uuid import uuid4
from datetime import datetime

# For this example, we'll use mock session and database
# In production, use: from src.database.session import get_async_session


async def main():
    """Demonstrate agent usage in a complete trading workflow."""

    print("=" * 80)
    print("RiseTrader Intelligent Agent System - Usage Example")
    print("=" * 80)

    # NOTE: In production, you would create agents from database records
    # For this example, we'll show the structure without DB connection

    symbol = "Gold"
    account_balance = 50000.0

    print(f"\n📊 Scenario: Analyzing {symbol} for 4H swing trade")
    print(f"💰 Account Balance: ${account_balance:,.2f}\n")

    # ========================================================================
    # PHASE 1: ANALYSIS LAYER
    # ========================================================================

    print("=" * 80)
    print("PHASE 1: ANALYSIS - Gathering Market Intelligence")
    print("=" * 80)

    # Example outputs (in production, these come from actual agent.run() calls)

    print("\n🔍 Technical Analysis (Qwen3-14B, ~1.5s)")
    print("-" * 80)
    technical_report = {
        "directional_bias": "BULLISH",
        "confidence": 0.75,
        "current_price": 2050.00,
        "support_levels": [2045.00, 2040.00, 2035.00],
        "resistance_levels": [2055.00, 2060.00, 2065.00],
        "model_agreement": 0.75,  # TCN, XGBoost, LSTM all agree
        "regime": "TRENDING_UP",
        "key_indicators": {
            "rsi": 58,
            "macd_signal": "BULLISH",
            "atr": 25.0,
            "adx": 28,
        },
        "forecast_summary": "ML models show 70% probability of move to $2060-2065",
        "risk_factors": [
            "RSI approaching overbought territory (>60)",
            "Resistance cluster at $2055-2060"
        ]
    }

    print(f"Bias: {technical_report['directional_bias']} ({technical_report['confidence']:.1%} confidence)")
    print(f"Current Price: ${technical_report['current_price']:.2f}")
    print(f"Regime: {technical_report['regime']} (ADX: {technical_report['key_indicators']['adx']})")
    print(f"Model Agreement: {technical_report['model_agreement']:.0%}")
    print(f"Support: {technical_report['support_levels'][:2]}")
    print(f"Resistance: {technical_report['resistance_levels'][:2]}")
    print(f"Forecast: {technical_report['forecast_summary']}")

    print("\n📰 Fundamental Analysis (Qwen3-14B, ~1.5s)")
    print("-" * 80)
    fundamental_report = {
        "macro_sentiment": "RISK_OFF",
        "macro_context": "USD weakness + geopolitical tensions supporting Gold demand",
        "upcoming_events": [
            {
                "event_name": "FOMC Meeting",
                "event_time": "2025-12-15T14:00:00Z",
                "importance": "HIGH",
                "expected_impact": "Potential USD volatility, could impact Gold $20-30"
            }
        ],
        "correlation_insights": {
            "usd_strength": "Strong inverse correlation (-0.82)",
            "equity_correlation": "Low correlation with S&P 500 (0.15)",
            "safe_haven_demand": "Elevated due to geopolitical concerns"
        },
        "fundamental_drivers": [
            "USD weakness driving Gold higher",
            "Central bank gold buying (Q4 2025)",
            "Real yields declining"
        ],
        "risk_factors": [
            "FOMC meeting in 3 days could reverse USD trend",
            "Gold/Silver ratio elevated (overextension risk)"
        ],
        "confidence": 0.70
    }

    print(f"Macro Sentiment: {fundamental_report['macro_sentiment']}")
    print(f"Context: {fundamental_report['macro_context']}")
    print(f"Next Event: {fundamental_report['upcoming_events'][0]['event_name']} (3 days)")
    print(f"Key Driver: {fundamental_report['fundamental_drivers'][0]}")

    print("\n💭 Sentiment Analysis (Qwen3-14B, ~1.5s)")
    print("-" * 80)
    sentiment_report = {
        "crowd_sentiment": "EXTREMELY_BULLISH",
        "crowd_metrics": {
            "retail_long_percent": 85,
            "fear_greed_index": 75,
            "sentiment_score": "Extreme greed"
        },
        "smart_money_flow": "DISTRIBUTING",
        "sentiment_divergence": True,
        "contrarian_signal": True,
        "order_flow_insights": {
            "large_buy_orders": "Concentrated at $2045-2048 (support)",
            "institutional_flow": "Net selling over last 3 sessions",
            "volume_profile": "High volume node at $2050 (current price)"
        },
        "sentiment_summary": "Retail 85% long while COT shows commercials reducing positions - bearish divergence",
        "risk_factors": [
            "Crowded long positioning (>80% retail long)",
            "Smart money distributing into retail buying"
        ],
        "confidence": 0.80
    }

    print(f"Crowd: {sentiment_report['crowd_sentiment']} ({sentiment_report['crowd_metrics']['retail_long_percent']}% long)")
    print(f"Smart Money: {sentiment_report['smart_money_flow']}")
    print(f"⚠️  Divergence: Retail bullish vs. Institutions selling")
    print(f"Contrarian Signal: {sentiment_report['contrarian_signal']} (extreme sentiment)")

    # ========================================================================
    # PHASE 2: SYNTHESIS
    # ========================================================================

    print("\n" + "=" * 80)
    print("SYNTHESIS: Combining Analysis Perspectives")
    print("=" * 80)

    print("\n✅ Bullish Factors:")
    print("  • Technical: BULLISH bias, TRENDING_UP regime, ML models 70% confident")
    print("  • Fundamental: RISK_OFF macro supporting Gold, USD weakness")
    print("  • Strong support at $2045-2048")

    print("\n⚠️  Risk Factors:")
    print("  • Sentiment: Extreme retail bullishness (85% long) - contrarian bearish")
    print("  • Smart money distributing (COT data)")
    print("  • FOMC meeting in 3 days (HIGH risk event)")
    print("  • Resistance cluster at $2055-2060")

    print("\n🎯 Trade Decision: LONG with REDUCED SIZE (sentiment divergence + event risk)")

    # ========================================================================
    # PHASE 3: DECISION LAYER
    # ========================================================================

    print("\n" + "=" * 80)
    print("PHASE 3: DECISION - Determining Trade Parameters")
    print("=" * 80)

    print("\n💰 Position Sizing (DeepSeek-R1-14B, ~10s)")
    print("-" * 80)

    # Context for sizing decision
    sizing_context = {
        "account_balance": account_balance,
        "current_drawdown": 0.03,  # 3% drawdown
        "trade_conviction": 0.70,  # Medium conviction (due to sentiment divergence)
        "win_rate": 0.60,
        "avg_win": 125,
        "avg_loss": 50,
        "market_regime": "TRENDING_UP",
        "correlation_with_existing": 0.0,  # No existing Gold positions
        "major_event_within_24h": False,
        "major_event_within_48h": True,  # FOMC in 3 days
    }

    position_decision = {
        "lot_quantity": 0.35,
        "dynamic_risk_percentage": 0.9,  # Reduced from normal 1.5% due to factors
        "kelly_fraction_applied": 0.12,  # Quarter-Kelly
        "base_size": 0.75,
        "adjustments": {
            "drawdown_reduction": 0.95,     # 5% reduction for 3% DD
            "volatility_adjustment": 0.85,  # 15% reduction for TRENDING (wider stops)
            "conviction_reduction": 0.85,   # 15% reduction for medium conviction
            "correlation_adjustment": 1.0,  # No existing positions
            "event_risk_reduction": 0.8     # 20% reduction for FOMC in 3 days
        },
        "reasoning": (
            "Kelly fraction 0.12 (from 60% win rate, 2.5:1 avg RR). "
            "Applied 5% drawdown reduction, 15% volatility adjustment for TRENDING regime, "
            "15% conviction reduction due to sentiment divergence, "
            "20% event risk reduction for upcoming FOMC. "
            "Final: 0.35 lots = 0.9% account risk."
        ),
        "confidence": 0.75,
        "risk_metrics": {
            "max_loss_usd": 437.50,
            "risk_reward_ratio": 2.0,
            "position_value_usd": 3500.00
        }
    }

    print(f"Position Size: {position_decision['lot_quantity']} lots")
    print(f"Risk: {position_decision['dynamic_risk_percentage']:.2f}% of account")
    print(f"Max Loss: ${position_decision['risk_metrics']['max_loss_usd']:.2f}")
    print(f"Kelly Fraction: {position_decision['kelly_fraction_applied']:.2f}")
    print(f"\nAdjustments Applied:")
    for factor, multiplier in position_decision['adjustments'].items():
        change = (multiplier - 1.0) * 100
        print(f"  • {factor}: {multiplier:.2f}x ({change:+.0f}%)")

    print("\n🛑 Stop-Loss Placement (DeepSeek-R1-14B, ~10s)")
    print("-" * 80)

    stop_decision = {
        "stop_price": 2037.50,
        "atr_distance_pips": 125,  # 12.5 pips
        "atr_multiplier": 2.0,  # Adaptive for TRENDING regime
        "placement_strategy": "HYBRID",
        "nearest_structure_level": 2040.00,
        "estimated_hit_probability": 0.20,
        "reasoning": (
            "Entry $2050. Support at $2045 (recent swing low), $2040 (strong level). "
            "ATR = 25 pips, regime TRENDING_UP suggests 2.0x ATR = 50 pips. "
            "HYBRID approach: Place stop below $2040 support at $2037.50 (125 pips) "
            "to avoid being stopped out at obvious levels. "
            "Distance: 125 pips (50 pips beyond structure)."
        ),
        "risk_factors": [
            "Support at $2040-2045 only tested twice (not heavily validated)",
            "Stop distance wider due to TRENDING regime (avoid noise)"
        ],
        "confidence": 0.80
    }

    entry_price = technical_report['current_price']
    stop_pips = (entry_price - stop_decision['stop_price']) * 10  # For Gold, 1 point = 10 pips

    print(f"Entry: ${entry_price:.2f}")
    print(f"Stop: ${stop_decision['stop_price']:.2f} ({stop_pips:.0f} pips)")
    print(f"Strategy: {stop_decision['placement_strategy']}")
    print(f"ATR Multiplier: {stop_decision['atr_multiplier']}x (adaptive for {technical_report['regime']})")
    print(f"Nearest Support: ${stop_decision['nearest_structure_level']:.2f}")
    print(f"Stop Hit Probability: {stop_decision['estimated_hit_probability']:.0%}")

    print("\n🎯 Take-Profit Targeting (DeepSeek-R1-14B, ~10s)")
    print("-" * 80)

    tp_decision = {
        "primary_target_price": 2075.00,
        "primary_target_pips": 250,  # 25 pips
        "dynamic_risk_reward_ratio": 2.0,  # 250 pips profit / 125 pips risk
        "estimated_reach_probability": 0.60,
        "expected_value": 112.50,  # (0.60 * 250) - (0.40 * 125) = 100 pips EV
        "partial_targets": [
            {
                "target_price": 2065.00,
                "close_percentage": 50,
                "estimated_probability": 0.70,
                "reasoning": "ML models show 70% probability to $2065 - take 50% profit here"
            },
            {
                "target_price": 2075.00,
                "close_percentage": 50,
                "estimated_probability": 0.60,
                "reasoning": "Let remainder run to resistance ($2075) with 60% probability"
            }
        ],
        "nearest_resistance_level": 2078.00,
        "reasoning": (
            "ML forecasts: 70% P($2065), 60% P($2075). "
            "Resistance at $2075-2078 (former swing high). "
            "Using partial targets maximizes EV: "
            "Take 50% at $2065 (high probability), "
            "let 50% run to $2075 (resistance). "
            "EV with partials: $112.50 vs. $100 full exit at $2065."
        ),
        "risk_factors": [
            "Strong resistance at $2075-2078 may cap upside",
            "FOMC event before full target may be reached"
        ],
        "confidence": 0.75
    }

    target_pips_1 = (tp_decision['partial_targets'][0]['target_price'] - entry_price) * 10
    target_pips_2 = (tp_decision['partial_targets'][1]['target_price'] - entry_price) * 10

    print(f"Strategy: Partial Targets (2-stage exit)")
    print(f"\n  Target 1 (50%): ${tp_decision['partial_targets'][0]['target_price']:.2f} ({target_pips_1:.0f} pips)")
    print(f"    Probability: {tp_decision['partial_targets'][0]['estimated_probability']:.0%}")
    print(f"    Reasoning: {tp_decision['partial_targets'][0]['reasoning']}")
    print(f"\n  Target 2 (50%): ${tp_decision['partial_targets'][1]['target_price']:.2f} ({target_pips_2:.0f} pips)")
    print(f"    Probability: {tp_decision['partial_targets'][1]['estimated_probability']:.0%}")
    print(f"    Reasoning: {tp_decision['partial_targets'][1]['reasoning']}")

    print(f"\nRisk-Reward: {tp_decision['dynamic_risk_reward_ratio']:.1f}:1")
    print(f"Expected Value: ${tp_decision['expected_value']:.2f}")

    # ========================================================================
    # PHASE 4: EXECUTION LAYER
    # ========================================================================

    print("\n" + "=" * 80)
    print("PHASE 4: EXECUTION - Trade Placement & Monitoring")
    print("=" * 80)

    print("\n⚡ Trade Execution (Qwen3-14B, ~0.5s + MT4 latency)")
    print("-" * 80)

    execution_result = {
        "order_id": "87654321",
        "status": "FILLED",
        "requested_price": 2050.00,
        "actual_fill_price": 2050.15,  # 1.5 pips slippage
        "requested_quantity": 0.35,
        "filled_quantity": 0.35,
        "slippage_pips": 1.5,
        "slippage_usd": 5.25,
        "execution_time_ms": 320,
        "commission_usd": 3.50,
        "rejection_reason": None,
        "mt4_response": {
            "ticket": 87654321,
            "price": 2050.15,
            "volume": 0.35,
            "timestamp": datetime.now().isoformat()
        }
    }

    print(f"✅ Order FILLED")
    print(f"Order ID: {execution_result['order_id']}")
    print(f"Requested: ${execution_result['requested_price']:.2f}")
    print(f"Filled: ${execution_result['actual_fill_price']:.2f}")
    print(f"Slippage: {execution_result['slippage_pips']:.1f} pips (${execution_result['slippage_usd']:.2f})")
    print(f"Commission: ${execution_result['commission_usd']:.2f}")
    print(f"Execution Time: {execution_result['execution_time_ms']:.0f}ms")

    print("\n👁️  Position Monitoring (Continuous)")
    print("-" * 80)
    print("Position Monitor agent will continuously check:")
    print("  • Trail stop to breakeven when price > entry + 2x risk")
    print("  • Scale out 50% at $2065 (Target 1)")
    print("  • Monitor for regime changes (TRENDING_UP → RANGING)")
    print("  • Check for invalidation (break below $2040 support)")
    print("  • Watch for FOMC event (close before if < 1 hour)")

    # ========================================================================
    # SUMMARY
    # ========================================================================

    print("\n" + "=" * 80)
    print("📋 TRADE SUMMARY")
    print("=" * 80)

    print(f"\nSymbol: {symbol}")
    print(f"Direction: LONG")
    print(f"Entry: ${execution_result['actual_fill_price']:.2f}")
    print(f"Stop: ${stop_decision['stop_price']:.2f} ({stop_pips:.0f} pips)")
    print(f"Target 1 (50%): ${tp_decision['partial_targets'][0]['target_price']:.2f}")
    print(f"Target 2 (50%): ${tp_decision['partial_targets'][1]['target_price']:.2f}")
    print(f"Position Size: {position_decision['lot_quantity']} lots")
    print(f"Risk: ${position_decision['risk_metrics']['max_loss_usd']:.2f} ({position_decision['dynamic_risk_percentage']:.2f}%)")
    print(f"Risk-Reward: {tp_decision['dynamic_risk_reward_ratio']:.1f}:1")
    print(f"Expected Value: ${tp_decision['expected_value']:.2f}")

    print("\n🎯 Key Decision Factors:")
    print(f"  • Technical: BULLISH with {technical_report['model_agreement']:.0%} model agreement")
    print(f"  • Fundamental: RISK_OFF macro supporting Gold")
    print(f"  • Sentiment: ⚠️  Extreme bullishness (contrarian caution)")
    print(f"  • Position Size: REDUCED due to sentiment + event risk")
    print(f"  • Stop Placement: HYBRID (structure + ATR adaptive)")
    print(f"  • Profit Strategy: PARTIAL TARGETS (maximize EV)")

    print("\n" + "=" * 80)
    print("✅ Intelligent Agent System Demonstration Complete")
    print("=" * 80)
    print("\nKey Advantages vs. Fixed Rules:")
    print("  ✓ Position size adapted to 5 risk factors (not fixed 2%)")
    print("  ✓ Stop placement considered structure + regime (not fixed 1.5x ATR)")
    print("  ✓ Target based on probabilities + EV (not fixed 2:1 RR)")
    print("  ✓ All decisions documented with clear reasoning")
    print("  ✓ Continuous monitoring and adaptive management")


if __name__ == "__main__":
    asyncio.run(main())
