import pandas as pd
import numpy as np
from backend.data_fetcher import calculate_vwap


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    avg = df["Volume"].rolling(window, min_periods=1).mean()
    return (df["Volume"] / avg.replace(0, np.nan)).fillna(1.0)


def _vwap_daily(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets at the start of each trading day."""
    result = pd.Series(index=df.index, dtype=float)
    for date, day_df in df.groupby(df.index.date):
        vwap = calculate_vwap(day_df)
        result.loc[day_df.index] = vwap.values
    return result


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    import config
    close = df["Close"]
    df = df.copy()
    df["EMA_9"] = _ema(close, config.EMA_FAST)
    df["EMA_21"] = _ema(close, config.EMA_SLOW)
    df["RSI"] = _rsi(close, config.RSI_PERIOD)
    df["ATR"] = _atr(df, config.ATR_PERIOD)
    df["VWAP"] = _vwap_daily(df)   # resets each day
    df["RVOL"] = _volume_ratio(df)

    # MACD
    ema_fast = _ema(close, config.MACD_FAST)
    ema_slow = _ema(close, config.MACD_SLOW)
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = _ema(df["MACD"], config.MACD_SIGNAL)
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # Bollinger Bands
    sma = close.rolling(config.BB_PERIOD).mean()
    std = close.rolling(config.BB_PERIOD).std()
    df["BB_Upper"] = sma + config.BB_STD * std
    df["BB_Mid"] = sma
    df["BB_Lower"] = sma - config.BB_STD * std

    return df
