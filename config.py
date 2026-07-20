import os
from dotenv import load_dotenv

load_dotenv()

# Watchlist - מניות לסריקה
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "AMD", "GOOGL",
    "NFLX", "COIN", "PLTR", "SOFI", "MARA", "RIOT", "SPY", "QQQ",
    "TQQQ", "SQQQ", "SNAP", "UBER", "HOOD", "BABA", "MU", "INTC",
]

# פרמטרי אינדיקטורים טכניים
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0
ATR_PERIOD = 14

# סף נפח יחסי לאות כניסה
VOLUME_RATIO_EMA = 1.5    # מינימום לאות EMA Cross
VOLUME_RATIO_VWAP = 2.0   # מינימום לאות VWAP Breakout
VOLUME_RATIO_ORB = 2.0    # מינימום לאות ORB

# פרמטרי Opening Range
ORB_MINUTES = 15  # 15 דקות ראשונות = 9:30-9:45 ET

# ניהול סיכונים
RISK_PER_TRADE_PCT = 0.01   # 1% סיכון לעסקה
REWARD_RISK_RATIO = 2.0     # יחס רווח:סיכון מינימלי 1:2
DAILY_LOSS_LIMIT_PCT = 0.05  # 5% הפסד יומי מקסימלי
ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "10000"))

# פילטרי מחיר ונפח (אין מגבלת מחיר עליונה - SPY/META/QQQ מעל $500)
MIN_PRICE = 2.0
MAX_PRICE = 5000.0
MIN_DAILY_VOLUME = 100_000

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# סריקה
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))

# שרת
HOST = "0.0.0.0"
PORT = 8000
