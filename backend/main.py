import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Set
import pytz

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import config
from backend.screener import run_screener, scan_stock
from backend.telegram_bot import send_signal_alert, send_text
from backend.data_fetcher import is_market_open

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

latest_data: dict = {"stocks": [], "signals": [], "last_scan": None, "market_open": False}
sent_signal_keys: Set[str] = set()


class WsManager:
    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws) if hasattr(self._connections, 'discard') else None
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)


manager = WsManager()


async def _scanner_loop():
    # Small initial delay so the server is up
    await asyncio.sleep(3)
    while True:
        try:
            logger.info("Running screener...")
            stocks = await run_screener()
            all_signals = []
            new_alerts = 0

            for stock in stocks:
                for sig in stock.get("signals", []):
                    all_signals.append(sig)
                    # Deduplicate: same symbol + strategy + hour
                    key = f"{sig['symbol']}_{sig['strategy']}_{sig['timestamp'][:13]}"
                    if key not in sent_signal_keys:
                        sent_signal_keys.add(key)
                        asyncio.create_task(send_signal_alert(sig))
                        new_alerts += 1

            now_str = datetime.now(ET).strftime("%H:%M:%S ET")
            latest_data.update({
                "stocks": stocks,
                "signals": all_signals,
                "last_scan": now_str,
                "market_open": is_market_open(),
            })

            await manager.broadcast({"type": "update", "data": latest_data})
            logger.info(f"Scan done: {len(stocks)} stocks, {len(all_signals)} signals, {new_alerts} new alerts")

        except Exception as e:
            logger.error(f"Screener error: {e}", exc_info=True)

        await asyncio.sleep(config.SCAN_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_scanner_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="TradingAlert Pro", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.get("/api/scan")
async def get_scan():
    return JSONResponse(latest_data)


@app.get("/api/watchlist")
async def get_watchlist():
    return JSONResponse({"symbols": config.WATCHLIST})


@app.get("/api/stock/{symbol}")
async def get_stock(symbol: str):
    data = await scan_stock(symbol.upper())
    if not data:
        return JSONResponse({"error": f"Could not fetch data for {symbol}"}, status_code=404)
    return JSONResponse(data)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    if latest_data["stocks"]:
        try:
            await websocket.send_json({"type": "update", "data": latest_data})
        except Exception:
            pass
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
