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

Four independent checkers, each returns an optional `Signal` dataclass:

| Checker | Trigger condition | Min RVOL |
|---|---|---|
| `check_ema_crossover` | EMA9 crosses EMA21, RSI not extreme | 1.5× |
| `check_vwap_breakout` | Price crosses VWAP, RSI confirms direction | 2.0× |
| `check_orb_breakout` | Price breaks first-15-min range after 9:45 ET | 2.0× |
| `check_rsi_reversal` | RSI crosses back through 30 or 70 | 1.5× |

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

- **VWAP resets daily** — `calculate_vwap()` in `data_fetcher.py` uses `cumsum()` over the entire DataFrame. Fetching `period="2d"` means VWAP accumulates from the start of the dataset, not midnight ET. For intraday VWAP accuracy, the 5m data should start at today's open.
- **yfinance timestamps** — the index is timezone-aware (ET). `sub.index.astype("int64") // 10**9` produces correct UTC UNIX seconds because pandas stores tz-aware datetimes as UTC internally.
- **WebSocket protocol** — `app.js` uses `wss://` when the page is served over HTTPS (Cloudflare Tunnel), `ws://` otherwise.
- **Signal deduplication** — `sent_signal_keys` in `main.py` uses `symbol_strategy_YYYY-MM-DDTHH` as key, so the same setup only fires one Telegram alert per hour.
- **Chart is initialized lazily** — `initChart()` in `app.js` runs only on the first `loadChart()` call. Subsequent stock selections reuse the same chart instance and call `setData()` to replace series data.
