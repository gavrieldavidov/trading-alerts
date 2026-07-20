import uvicorn
import sys
import os
import subprocess
import threading
import re

sys.path.insert(0, os.path.dirname(__file__))

from backend.main import app


def start_tunnel():
    """Start cloudflared tunnel and print the public URL."""
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', line)
            if match:
                url = match.group(0)
                print("\n" + "="*55, flush=True)
                print(f"  🌍  PUBLIC URL: {url}", flush=True)
                print("="*55 + "\n", flush=True)
                # Keep reading output so the pipe doesn't block cloudflared
                for _ in proc.stdout:
                    pass
                break
        proc.wait()
    except FileNotFoundError:
        print("  ⚠️  cloudflared לא מותקן — רץ רק על localhost")
    except Exception as e:
        print(f"  ⚠️  Tunnel error: {e}")


PUBLIC = "--public" in sys.argv or "-p" in sys.argv

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  📈  TradingAlert Pro — US Day Trading Platform")
    print("="*55)
    print("  Dashboard:  http://localhost:8000")
    print("  הוסף --public לקבלת URL ציבורי (Cloudflare)")
    print("="*55 + "\n")

    if PUBLIC:
        print("  🔄  מפעיל Cloudflare Tunnel...")
        t = threading.Thread(target=start_tunnel, daemon=True)
        t.start()

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="info")
