"""Yerel izleme paneli: http://localhost:8742

Paper trader'in state.json'unu okuyup tarayicida gosterir. Sayfa 60 saniyede
bir kendini yeniler. Hicbir veri disari gitmez, tamamen yerel calisir.

Kullanim: .venv/bin/python dashboard.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8742
STATE_FILE = Path(__file__).resolve().parent / "paper" / "state.json"
INITIAL = 10_000.0


def fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m %H:%M")
    except (ValueError, TypeError):
        return iso or "-"


def sparkline(history: list) -> str:
    eqs = [h["equity"] for h in history][-200:]
    if len(eqs) < 2:
        return "<p style='color:#888'>Henuz yeterli veri yok — her dongude bir nokta eklenir.</p>"
    lo, hi = min(eqs), max(eqs)
    rng = (hi - lo) or 1.0
    w, h = 640, 120
    pts = " ".join(
        f"{i * w / (len(eqs) - 1):.1f},{h - (e - lo) / rng * (h - 10) - 5:.1f}"
        for i, e in enumerate(eqs)
    )
    color = "#1D9E75" if eqs[-1] >= INITIAL else "#D85A30"
    base_y = h - (INITIAL - lo) / rng * (h - 10) - 5 if lo <= INITIAL <= hi else None
    base = (f"<line x1='0' y1='{base_y:.1f}' x2='{w}' y2='{base_y:.1f}' "
            f"stroke='#999' stroke-dasharray='4 4' stroke-width='1'/>") if base_y else ""
    return (f"<svg viewBox='0 0 {w} {h}' style='width:100%;max-width:{w}px'>{base}"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2'/></svg>")


def render() -> str:
    if not STATE_FILE.exists():
        return ("<h1>trading-bot</h1><p>Henuz veri yok. Once paper trader'i calistir:"
                "<br><code>.venv/bin/python paper_trader.py</code></p>")
    s = json.loads(STATE_FILE.read_text())
    hist = s.get("history", [])
    prices = hist[-1]["prices"] if hist else {}
    eq = hist[-1]["equity"] if hist else s["cash"]
    ret = eq / INITIAL - 1
    color = "#1D9E75" if ret >= 0 else "#C0392B"
    last_update = fmt_ts(hist[-1]["ts"]) if hist else "-"

    pos_rows = ""
    for sym, p in s.get("positions", {}).items():
        cur = prices.get(sym, p["entry_price"])
        upnl = p["side"] * p["qty"] * (cur - p["entry_price"])
        pos_rows += (f"<tr><td>{sym}</td><td>{'LONG' if p['side'] == 1 else 'SHORT'}</td>"
                     f"<td>{p['qty']:.6f}</td><td>{p['entry_price']:,.2f}</td>"
                     f"<td>{cur:,.2f}</td><td>{p['stop_price']:,.2f}</td>"
                     f"<td style='color:{'#1D9E75' if upnl >= 0 else '#C0392B'}'>{upnl:+,.2f}$</td>"
                     f"<td>{fmt_ts(p['entry_time'])}</td></tr>")
    if not pos_rows:
        pos_rows = "<tr><td colspan='8' style='color:#888'>Acik pozisyon yok — bot sinyal bekliyor</td></tr>"

    trade_rows = ""
    for t in reversed(s.get("trades", [])[-20:]):
        trade_rows += (f"<tr><td>{t['symbol']}</td><td>{'LONG' if t['side'] == 1 else 'SHORT'}</td>"
                       f"<td>{t['entry_price']:,.2f}</td><td>{t['exit_price']:,.2f}</td>"
                       f"<td style='color:{'#1D9E75' if t['pnl'] >= 0 else '#C0392B'}'>{t['pnl']:+,.2f}$</td>"
                       f"<td>{t['reason']}</td><td>{fmt_ts(t['exit_time'])}</td></tr>")
    if not trade_rows:
        trade_rows = "<tr><td colspan='7' style='color:#888'>Henuz kapanan islem yok</td></tr>"

    price_txt = "  ·  ".join(f"{k} {v:,.0f}$" for k, v in prices.items())

    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60"><title>trading-bot paneli</title>
<style>
body{{font-family:-apple-system,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-bottom:2rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eee}}
th{{color:#888;font-weight:500;font-size:12px}}
h1{{font-size:20px}} h2{{font-size:15px;color:#555;margin-top:2rem}}
.big{{font-size:36px;font-weight:600;color:{color}}}
.muted{{color:#888;font-size:13px}}
@media(prefers-color-scheme:dark){{body{{background:#1a1a1a;color:#ddd}}th,td{{border-color:#333}}}}
</style></head><body>
<h1>trading-bot — paper trading</h1>
<p class="muted">Sanal para, gercek fiyatlar. Son guncelleme: {last_update} UTC · {price_txt}</p>
<div class="big">{eq:,.2f}$ <span style="font-size:18px">({ret:+.2%})</span></div>
<p class="muted">Baslangic: {INITIAL:,.0f}$ · {fmt_ts(s.get('started_at', ''))} tarihinden beri</p>
{sparkline(hist)}
<h2>Acik pozisyonlar</h2>
<table><tr><th>Sembol</th><th>Yon</th><th>Miktar</th><th>Giris</th><th>Guncel</th><th>Stop</th><th>PnL</th><th>Acilis</th></tr>{pos_rows}</table>
<h2>Son islemler</h2>
<table><tr><th>Sembol</th><th>Yon</th><th>Giris</th><th>Cikis</th><th>PnL</th><th>Sebep</th><th>Zaman</th></tr>{trade_rows}</table>
<p class="muted">Sayfa 60 sn'de bir yenilenir. Bot her 4 saatlik bar kapanisinda karar verir.</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Panel hazir: http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
