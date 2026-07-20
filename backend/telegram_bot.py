import httpx
import config

STRATEGY_NAMES = {
    "EMA_CROSS": "EMA Cross 9/21",
    "VWAP_BREAK": "VWAP Breakout",
    "ORB": "Opening Range Breakout",
    "RSI_REVERSAL": "RSI Reversal",
}


def _format_signal(signal: dict) -> str:
    arrow = "🟢 קנייה" if signal["signal_type"] == "BUY" else "🔴 מכירה"
    strategy = STRATEGY_NAMES.get(signal["strategy"], signal["strategy"])
    ts = signal["timestamp"][:16].replace("T", " ")

    return (
        f"{arrow} — <b>{signal['symbol']}</b>\n"
        f"📊 אסטרטגיה: {strategy}\n"
        f"💰 כניסה: <b>${signal['entry_price']}</b>\n"
        f"🛑 Stop Loss: ${signal['stop_loss']}\n"
        f"🎯 יעד 1 (2R): ${signal['target_1']}\n"
        f"🎯 יעד 2 (3R): ${signal['target_2']}\n"
        f"📈 RSI: {signal['rsi']} | RVOL: {signal['rvol']}x\n"
        f"📦 גודל פוזיציה: {signal['position_size']} מניות\n"
        f"⚖️ יחס רווח:סיכון 1:{signal['risk_reward']}\n"
        f"⏰ {ts}"
    )


async def send_signal_alert(signal: dict) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": _format_signal(signal),
                "parse_mode": "HTML",
            })
            return resp.status_code == 200
    except Exception:
        return False


async def send_text(message: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            })
            return resp.status_code == 200
    except Exception:
        return False
