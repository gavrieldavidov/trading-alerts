import asyncio
import math
from typing import List, Optional, Dict, Any
import pandas as pd

import config
from backend.data_fetcher import get_intraday_data
from backend.indicators import add_all_indicators
from backend.signals import generate_signals


def _df_to_chart_records(df: pd.DataFrame) -> List[Dict]:
    cols = ["Open", "High", "Low", "Close", "Volume",
            "EMA_9", "EMA_21", "VWAP", "RSI", "ATR", "MACD", "MACD_Signal", "MACD_Hist"]
    # Show today's session only so the chart is not compressed by weekend gaps
    today = df.index[-1].date()
    today_df = df[df.index.date == today]
    sub = today_df[[c for c in cols if c in today_df.columns]].copy()
    if len(sub) == 0:
        sub = df[[c for c in cols if c in df.columns]].tail(80).copy()
    # Convert timezone-aware datetime index to UNIX seconds
    sub["time"] = sub.index.astype("int64") // 10**9
    records = []
    for row in sub.itertuples(index=False):
        rec: Dict[str, Any] = {}
        for field_name, val in zip(sub.columns, row):
            if isinstance(val, float):
                rec[field_name] = None if math.isnan(val) else round(val, 4)
            else:
                rec[field_name] = val
        records.append(rec)
    return records


async def scan_stock(symbol: str) -> Optional[Dict]:
    try:
        df = get_intraday_data(symbol, interval="5m", period="2d")
        if df.empty or len(df) < 20:
            return None

        # Drop the last (in-progress) bar when market is open to avoid incomplete volume
        from backend.data_fetcher import is_market_open
        if is_market_open() and len(df) > 20:
            df = df.iloc[:-1]

        price = float(df["Close"].iloc[-1])
        if not (config.MIN_PRICE <= price <= config.MAX_PRICE):
            return None

        df = add_all_indicators(df)

        curr = df.iloc[-1]
        first_price = float(df["Close"].iloc[0])
        change_pct = ((price - first_price) / first_price * 100) if first_price else 0

        signals = generate_signals(symbol, df)
        chart_data = _df_to_chart_records(df)

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(df["Volume"].sum()),
            "rvol": round(float(curr.get("RVOL", 1.0)), 2),
            "rsi": round(float(curr.get("RSI", 50)), 1),
            "atr": round(float(curr.get("ATR", 0)), 4),
            "vwap": round(float(curr.get("VWAP", price)), 2),
            "ema_9": round(float(curr.get("EMA_9", price)), 2),
            "ema_21": round(float(curr.get("EMA_21", price)), 2),
            "signals": [s.to_dict() for s in signals],
            "chart_data": chart_data,
        }
    except Exception as e:
        return None


async def run_screener() -> List[Dict]:
    results = []
    failed = []

    for symbol in config.WATCHLIST:
        result = await scan_stock(symbol)
        if result:
            results.append(result)
        else:
            failed.append(symbol)
        await asyncio.sleep(0.15)

    # Retry failed symbols once with a longer wait
    if failed:
        await asyncio.sleep(2.0)
        for symbol in failed:
            result = await scan_stock(symbol)
            if result:
                results.append(result)
            await asyncio.sleep(0.3)

    results.sort(key=lambda x: (-(len(x.get("signals", []))), -x.get("rvol", 0)))
    return results
