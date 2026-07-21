# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

```bash
# Install dependencies (Python 3.9+)
pip3 install -r requirements.txt

# Start server — localhost only
python3 run.py

# Start server with public Cloudflare Tunnel URL
python3 run.py --public
```

Dashboard is served at `http://localhost:8000`. The first screener scan completes ~35 seconds after startup (24 stocks × ~1.5s each including rate-limit sleeps).

## Configuration

All tunable parameters live in `config.py` — indicator periods, signal thresholds (VOLUME_RATIO_EMA/VWAP/ORB), risk management (RISK_PER_TRADE_PCT, REWARD_RISK_RATIO), price filters, and the WATCHLIST.

Runtime overrides via `.env` (copy from `.env.example`): `ACCOUNT_SIZE`, `SCAN_INTERVAL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

**The frontend WATCHLIST array in `frontend/app.js` must be kept in sync with `config.py` WATCHLIST** — the JS array is what always populates the sidebar; the Python list is what gets scanned.

## Architecture

The pipeline for each scan cycle:

```
run_screener() [screener.py]
  └── scan_stock(symbol) per symbol
        ├── get_intraday_data()   [data_fetcher.py]  — yfinance 5m bars, 2d period
        ├── add_all_indicators()  [indicators.py]    — adds EMA9/21, RSI, ATR, VWAP, RVOL, MACD, BB columns
        └── generate_signals()   [signals.py]        — runs 4 checkers, returns Signal dataclasses

FastAPI background task [main.py] calls run_screener() every SCAN_INTERVAL seconds,
broadcasts results via WebSocket to all connected browser clients,
and fires Telegram alerts for new signals (deduplicated by symbol+strategy+hour key).
```

**Data flow to frontend:** `scan_stock()` returns a dict that includes both summary stats and `chart_data` — a list of OHLCV + indicator rows with `time` as UNIX seconds (UTC). The frontend TradingView Lightweight Charts v4 library consumes this directly.

## Signal generation (`backend/signals.py`)

Six independent checkers, each returns an optional `Signal` dataclass:

| Checker | Trigger condition | Min RVOL config key |
|---|---|---|
| `check_ema_crossover` | EMA9 crosses EMA21, RSI not extreme | `VOLUME_RATIO_EMA` (1.0) |
| `check_vwap_breakout` | Price crosses VWAP, RSI confirms direction | `VOLUME_RATIO_VWAP` (1.3) |
| `check_orb_breakout` | Price breaks first-15-min range after 9:45 ET | `VOLUME_RATIO_ORB` (1.3) |
| `check_rsi_reversal` | RSI crosses back through 30 or 70 | `VOLUME_RATIO_EMA` (1.0) |
| `check_macd_crossover` | MACD line crosses Signal line, MACD near zero | `VOLUME_RATIO_MACD` (1.0) |
| `check_bb_breakout` | Price breaks above BB_Upper or below BB_Lower | `VOLUME_RATIO_BB` (1.2) |

All checkers call `_risk_levels()` which derives stop (1.5× ATR), target_1 (2R), target_2 (3R), and position size from `ACCOUNT_SIZE × RISK_PER_TRADE_PCT / stop_distance`.

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Serves `frontend/index.html` |
| `GET /api/scan` | Latest screener snapshot (all stocks + signals) |
| `GET /api/stock/{symbol}` | On-demand single-stock scan (used when clicking an unscanned symbol) |
| `GET /api/watchlist` | Static symbol list from config |
| `WS /ws` | Real-time push; sends `{"type": "update", "data": {...}}` after each scan |

## Key implementation details

- **VWAP resets daily** — `_vwap_daily()` in `indicators.py` groups by `df.index.date` and calls `calculate_vwap()` per day, so VWAP resets at midnight ET. The raw `calculate_vwap()` in `data_fetcher.py` is cumulative and should not be called directly on multi-day data.
- **Incomplete bar dropped** — `scan_stock()` removes `df.iloc[-1]` when `is_market_open()` is true, preventing the in-progress 5-minute bar's low volume from suppressing RVOL to near-zero.
- **Chart data is today only** — `_df_to_chart_records()` filters to `df.index.date == today` so the chart is never compressed by a weekend gap.
- **yfinance timestamps** — the index is timezone-aware (ET). `sub.index.astype("int64") // 10**9` produces correct UTC UNIX seconds because pandas stores tz-aware datetimes as UTC internally.
- **WebSocket protocol** — `app.js` uses `wss://` when the page is served over HTTPS (Cloudflare Tunnel), `ws://` otherwise.
- **Signal deduplication** — `sent_signal_keys` in `main.py` uses `symbol_strategy_YYYY-MM-DDTHH` as key, so the same setup only fires one Telegram alert per hour.
- **Chart is initialized lazily** — `initChart()` in `app.js` runs only on the first `loadChart()` call. Subsequent stock selections reuse the same chart instance and call `setData()` to replace series data.
- **Telegram strategy names** — `telegram_bot.py` has a `STRATEGY_NAMES` dict that maps strategy keys to Hebrew-friendly labels. If a new strategy is added to `signals.py`, add a matching entry there too.
- **Render.com deployment** — `Procfile` contains `web: python run.py`. PORT env var is read from `os.getenv("PORT", 8000)` in `run.py`.
