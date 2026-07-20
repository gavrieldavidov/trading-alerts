from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import math
import pandas as pd
import pytz

ET = pytz.timezone("America/New_York")


@dataclass
class Signal:
    symbol: str
    signal_type: str    # "BUY" | "SELL"
    strategy: str       # "EMA_CROSS" | "VWAP_BREAK" | "ORB" | "RSI_REVERSAL"
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    rsi: float
    rvol: float
    atr: float
    position_size: int
    risk_amount: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(ET))

    @property
    def stop_distance(self) -> float:
        if self.signal_type == "BUY":
            return self.entry_price - self.stop_loss
        return self.stop_loss - self.entry_price

    @property
    def risk_reward(self) -> float:
        sd = self.stop_distance
        if sd <= 0:
            return 0
        reward = (self.target_1 - self.entry_price) if self.signal_type == "BUY" else (self.entry_price - self.target_1)
        return round(reward / sd, 2)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "strategy": self.strategy,
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "rsi": round(self.rsi, 1),
            "rvol": round(self.rvol, 2),
            "atr": round(self.atr, 4),
            "position_size": self.position_size,
            "risk_amount": round(self.risk_amount, 2),
            "risk_reward": self.risk_reward,
            "timestamp": self.timestamp.isoformat(),
        }


def _risk_levels(entry: float, atr: float, direction: str) -> Optional[tuple]:
    import config
    stop_dist = max(1.5 * atr, entry * 0.005)  # at least 0.5% away
    if direction == "BUY":
        stop_loss = entry - stop_dist
        target_1 = entry + config.REWARD_RISK_RATIO * stop_dist
        target_2 = entry + 3 * stop_dist
    else:
        stop_loss = entry + stop_dist
        target_1 = entry - config.REWARD_RISK_RATIO * stop_dist
        target_2 = entry - 3 * stop_dist

    risk_amount = config.ACCOUNT_SIZE * config.RISK_PER_TRADE_PCT
    position_size = max(1, math.floor(risk_amount / stop_dist))
    return stop_loss, target_1, target_2, position_size, risk_amount


def check_ema_crossover(symbol: str, df: pd.DataFrame) -> Optional[Signal]:
    import config
    if len(df) < 25:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    rvol = float(curr.get("RVOL", 0))
    if rvol < config.VOLUME_RATIO_EMA:
        return None

    prev_bull = float(prev["EMA_9"]) > float(prev["EMA_21"])
    curr_bull = float(curr["EMA_9"]) > float(curr["EMA_21"])

    if curr_bull and not prev_bull:
        direction = "BUY"
    elif not curr_bull and prev_bull:
        direction = "SELL"
    else:
        return None

    rsi = float(curr["RSI"])
    if direction == "BUY" and rsi > 70:
        return None
    if direction == "SELL" and rsi < 30:
        return None

    entry = float(curr["Close"])
    atr = float(curr["ATR"])
    levels = _risk_levels(entry, atr, direction)
    if not levels:
        return None
    stop_loss, target_1, target_2, pos_size, risk = levels

    return Signal(symbol, direction, "EMA_CROSS", entry, stop_loss, target_1, target_2,
                  rsi, rvol, atr, pos_size, risk)


def check_vwap_breakout(symbol: str, df: pd.DataFrame) -> Optional[Signal]:
    import config
    if len(df) < 5:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    rvol = float(curr.get("RVOL", 0))
    if rvol < config.VOLUME_RATIO_VWAP:
        return None

    prev_above = float(prev["Close"]) > float(prev["VWAP"])
    curr_above = float(curr["Close"]) > float(curr["VWAP"])

    if curr_above and not prev_above:
        direction = "BUY"
    elif not curr_above and prev_above:
        direction = "SELL"
    else:
        return None

    rsi = float(curr["RSI"])
    if direction == "BUY" and rsi < 45:
        return None
    if direction == "SELL" and rsi > 55:
        return None

    entry = float(curr["Close"])
    atr = float(curr["ATR"])
    levels = _risk_levels(entry, atr, direction)
    if not levels:
        return None
    stop_loss, target_1, target_2, pos_size, risk = levels

    return Signal(symbol, direction, "VWAP_BREAK", entry, stop_loss, target_1, target_2,
                  rsi, rvol, atr, pos_size, risk)


def check_orb_breakout(symbol: str, df: pd.DataFrame) -> Optional[Signal]:
    import config
    if len(df) < 4:
        return None

    today = df.index[-1].date()
    today_df = df[df.index.date == today]
    if today_df.empty:
        return None

    import pandas as pd
    market_open = pd.Timestamp(f"{today} 09:30:00").tz_localize(ET)
    orb_end = pd.Timestamp(f"{today} 09:45:00").tz_localize(ET)

    orb_df = today_df[(today_df.index >= market_open) & (today_df.index < orb_end)]
    if len(orb_df) < 2:
        return None

    orb_high = float(orb_df["High"].max())
    orb_low = float(orb_df["Low"].min())

    curr_time = df.index[-1]
    if curr_time < orb_end:
        return None

    rvol = float(df.iloc[-1].get("RVOL", 0))
    if rvol < config.VOLUME_RATIO_ORB:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    curr_close = float(curr["Close"])
    prev_close = float(prev["Close"])
    rsi = float(curr["RSI"])

    if curr_close > orb_high and prev_close <= orb_high:
        direction = "BUY"
    elif curr_close < orb_low and prev_close >= orb_low:
        direction = "SELL"
    else:
        return None

    entry = curr_close
    atr = float(curr["ATR"])
    levels = _risk_levels(entry, atr, direction)
    if not levels:
        return None
    stop_loss, target_1, target_2, pos_size, risk = levels

    return Signal(symbol, direction, "ORB", entry, stop_loss, target_1, target_2,
                  rsi, rvol, atr, pos_size, risk)


def check_rsi_reversal(symbol: str, df: pd.DataFrame) -> Optional[Signal]:
    import config
    if len(df) < 15:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    rvol = float(curr.get("RVOL", 0))
    if rvol < config.VOLUME_RATIO_EMA:
        return None

    prev_rsi = float(prev["RSI"])
    curr_rsi = float(curr["RSI"])

    if prev_rsi < config.RSI_OVERSOLD and curr_rsi >= config.RSI_OVERSOLD:
        direction = "BUY"
    elif prev_rsi > config.RSI_OVERBOUGHT and curr_rsi <= config.RSI_OVERBOUGHT:
        direction = "SELL"
    else:
        return None

    entry = float(curr["Close"])
    atr = float(curr["ATR"])
    levels = _risk_levels(entry, atr, direction)
    if not levels:
        return None
    stop_loss, target_1, target_2, pos_size, risk = levels

    return Signal(symbol, direction, "RSI_REVERSAL", entry, stop_loss, target_1, target_2,
                  curr_rsi, rvol, atr, pos_size, risk)


def generate_signals(symbol: str, df: pd.DataFrame) -> List[Signal]:
    signals = []
    for checker in [check_ema_crossover, check_vwap_breakout, check_orb_breakout, check_rsi_reversal]:
        try:
            signal = checker(symbol, df)
            if signal:
                signals.append(signal)
        except Exception:
            pass
    return signals
