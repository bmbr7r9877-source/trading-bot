"""Gunluk ozet rapor: paper/state.json'dan okunabilir bir metin uretir.

Iki is yapar:
  1) paper/report.txt'e insan-okur ozet yazar (her zaman; commit'lenir, telefona
     ve GitHub'a akar — sifir kurulum).
  2) NTFY_TOPIC ortam degiskeni tanimliysa ayni ozeti ntfy.sh uzerinden telefona
     GERCEK push bildirimi olarak yollar (hesapsiz, ucretsiz). Bkz. README.

Kullanim:
  .venv/bin/python report.py            # raporu uret/yaz (+ NTFY varsa gonder)
  .venv/bin/python report.py --force    # saat penceresine bakma, her zaman gonder

Bildirim penceresi: yalnizca sabah (04:xx UTC = 07:xx TR) ve aksam (16:xx UTC =
19:xx TR) dongulerinde push atilir ki gun boyu spam olmasin. report.txt ise her
dongude guncellenir.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

PAPER_DIR = Path(__file__).resolve().parent / "paper"
STATE_FILE = PAPER_DIR / "state.json"
REPORT_FILE = PAPER_DIR / "report.txt"
INITIAL_EQUITY = 10_000.0

# push atilacak UTC saatleri (workflow :10'da kostugu icin 4 ve 16 = TR 07 ve 19)
NOTIFY_HOURS = {4, 16}


def _equity_at(history: list, target: datetime) -> float | None:
    """target zamanindan onceki en son equity noktasini bulur."""
    best = None
    for h in history:
        ts = datetime.fromisoformat(h["ts"])
        if ts <= target:
            best = h["equity"]
        else:
            break
    return best


def build_report(state: dict) -> tuple[str, str]:
    """(baslik, govde) doner."""
    history = state.get("history", [])
    now_eq = history[-1]["equity"] if history else state["cash"]
    prices = history[-1]["prices"] if history else {}
    total_ret = now_eq / INITIAL_EQUITY - 1

    now = datetime.now(timezone.utc)
    eq_24h = _equity_at(history, now - timedelta(hours=24))
    day_ret = (now_eq / eq_24h - 1) if eq_24h else 0.0
    eq_7d = _equity_at(history, now - timedelta(days=7))
    week_ret = (now_eq / eq_7d - 1) if eq_7d else None

    arrow = "🟢" if day_ret >= 0 else "🔴"
    title = f"{arrow} Bot {now_eq:,.0f}$ ({total_ret:+.1%})  gun {day_ret:+.1%}"

    lines = [
        f"📊 PAPER TRADING — {now.strftime('%Y-%m-%d %H:%M')} UTC",
        f"Bakiye: {now_eq:,.2f}$   (baslangic 10.000$, toplam {total_ret:+.1%})",
        f"Son 24s: {day_ret:+.2%}" + (f"   son 7g: {week_ret:+.2%}" if week_ret is not None else ""),
        "",
    ]

    positions = state.get("positions", {})
    if positions:
        lines.append("Acik pozisyonlar:")
        for sym, p in positions.items():
            yon = "LONG" if p["side"] == 1 else "SHORT"
            px = prices.get(sym, p["entry_price"])
            upnl = p["side"] * p["qty"] * (px - p["entry_price"])
            lines.append(f"  {sym} {yon}  giris {p['entry_price']:,.2f} → {px:,.2f}  "
                         f"({upnl:+.2f}$)")
    else:
        lines.append("Acik pozisyon yok (nakit bekliyor).")
    lines.append("")

    # son 24 saatte kapanan islemler
    recent = [t for t in state.get("trades", [])
              if datetime.fromisoformat(t["exit_time"]) >= now - timedelta(hours=24)]
    if recent:
        lines.append(f"Son 24s kapanan {len(recent)} islem:")
        for t in recent:
            yon = "long" if t["side"] == 1 else "short"
            lines.append(f"  {t['symbol']} {yon}  {t['pnl']:+.2f}$  ({t['reason']})")
    else:
        lines.append("Son 24s'te kapanan islem yok.")

    return title, "\n".join(lines)


def send_ntfy(title: str, body: str) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    try:
        requests.post(
            f"{server}/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Tags": "chart_with_upwards_trend"},
            timeout=15,
        ).raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"ntfy gonderilemedi: {e}")
        return False


def main():
    if not STATE_FILE.exists():
        print("state.json yok, rapor uretilemedi.")
        return
    state = json.loads(STATE_FILE.read_text())
    title, body = build_report(state)

    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(title + "\n\n" + body + "\n")
    print(body)

    # elle tetiklenen koşumlar (GitHub'da "Run workflow" ya da --force) her zaman
    # bildirim atar — test ve anlik kontrol icin. Otomatik koşumlar pencereye uyar.
    force = "--force" in sys.argv or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    in_window = datetime.now(timezone.utc).hour in NOTIFY_HOURS
    if force or in_window:
        if send_ntfy(title, body):
            print("\n[push gonderildi]")
    else:
        print("\n[bildirim penceresi disinda — sadece report.txt guncellendi]")


if __name__ == "__main__":
    main()
