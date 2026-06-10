"""Canli paper trading: GERCEK Binance fiyatlari, SANAL para.

Hicbir borsa hesabi/API anahtari gerekmez — fiyatlar public API'den okunur,
emirler yerel olarak simule edilir. Backtest motoruyla ayni strateji, ayni
risk kurallari calisir; tek fark verinin canli akmasi.

Kullanim:
  .venv/bin/python paper_trader.py            # tek dongu (cron icin)
  .venv/bin/python paper_trader.py --loop     # surekli: her 4 saatte bir dongu
  .venv/bin/python paper_trader.py --reset    # sanal hesabi sifirla (10.000$)

Durum results/paper/state.json'da tutulur; dashboard.py bu dosyayi okur.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from botlib import data, strategies
from botlib.risk import RiskConfig, RiskManager

# Konfigurasyon research.py taramasindan (train Sharpe + min 12 islem sarti):
INSTRUMENTS = [
    {"symbol": "BTCUSDT", "tf": "8h", "strategy": "trend_following",
     "params": {"fast": 20, "slow": 100, "allow_short": True}},
    {"symbol": "ETHUSDT", "tf": "4h", "strategy": "momentum_breakout",
     "params": {"entry_n": 24, "exit_n": 12, "allow_short": False}},
]
COMMISSION = 0.001
SLIPPAGE = 0.0003
INITIAL_EQUITY = 10_000.0

# paper/ git'te izlenir: GitHub Actions her dongude state.json'u commit'ler,
# telefon uygulamasi raw.githubusercontent.com'dan okur
PAPER_DIR = Path(__file__).resolve().parent / "paper"
STATE_FILE = PAPER_DIR / "state.json"
LOG_FILE = PAPER_DIR / "log.txt"


def log(msg: str):
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cash": INITIAL_EQUITY,
        "positions": {},
        "trades": [],
        "history": [],
        "last_bar": {},
        "day": None,
        "day_start_equity": INITIAL_EQUITY,
        "day_blocked": False,
    }


def save_state(state: dict):
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def mark_equity(state: dict, prices: dict) -> float:
    unreal = sum(
        p["side"] * p["qty"] * (prices.get(sym, p["entry_price"]) - p["entry_price"])
        for sym, p in state["positions"].items()
    )
    return state["cash"] + unreal


def close_position(state: dict, sym: str, price: float, reason: str):
    p = state["positions"].pop(sym)
    fill = price * (1 - p["side"] * SLIPPAGE)
    fees = (p["entry_price"] + fill) * p["qty"] * COMMISSION
    pnl = p["side"] * p["qty"] * (fill - p["entry_price"]) - fees
    state["cash"] += pnl
    state["trades"].append({
        "symbol": sym, "strategy": p["strategy"], "side": p["side"], "qty": p["qty"],
        "entry_time": p["entry_time"], "entry_price": p["entry_price"],
        "exit_time": datetime.now(timezone.utc).isoformat(), "exit_price": fill,
        "pnl": round(pnl, 2), "reason": reason,
    })
    log(f"KAPAT {sym} {'long' if p['side'] == 1 else 'short'} @ {fill:.2f} "
        f"pnl {pnl:+.2f}$ ({reason})")


def cycle(risk: RiskManager):
    state = load_state()
    prices: dict[str, float] = {}

    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        try:
            raw = data.fetch_binance(sym, inst["tf"], days=120, use_cache=False)
        except Exception as e:
            log(f"HATA {sym} veri cekilemedi: {e}")
            continue
        prepared = strategies.REGISTRY[inst["strategy"]](raw, **inst["params"])
        bar = prepared.iloc[-1]
        bar_time = prepared.index[-1].isoformat()
        prices[sym] = float(bar["close"])

        # ayni kapanmis bari iki kez isleme
        if state["last_bar"].get(sym) == bar_time:
            continue
        state["last_bar"][sym] = bar_time

        p = state["positions"].get(sym)

        # 1) stop kontrolu (son barin high/low'u ile)
        if p:
            if p["side"] == 1 and bar["low"] <= p["stop_price"]:
                close_position(state, sym, min(float(bar["close"]), p["stop_price"]), "stop")
                p = None
            elif p["side"] == -1 and bar["high"] >= p["stop_price"]:
                close_position(state, sym, max(float(bar["close"]), p["stop_price"]), "stop")
                p = None

        # 2) cikis sinyali
        if p and ((p["side"] == 1 and bar["exit_long_now"]) or
                  (p["side"] == -1 and bar["exit_short_now"])):
            close_position(state, sym, float(bar["close"]), "signal")
            p = None

        # 3) trailing stop
        if p and p["trail_mult"] > 0:
            if p["side"] == 1:
                p["stop_price"] = max(p["stop_price"], float(bar["close"]) - p["trail_mult"] * float(bar["atr"]))
            else:
                p["stop_price"] = min(p["stop_price"], float(bar["close"]) + p["trail_mult"] * float(bar["atr"]))

        # 4) giris sinyali
        if sym not in state["positions"] and int(bar["entry_now"]) != 0 and not state["day_blocked"]:
            side = int(bar["entry_now"])
            open_sides = {s: pp["side"] for s, pp in state["positions"].items()}
            if risk.allow_entry(sym, side, open_sides):
                eq = mark_equity(state, prices)
                qty, stop_dist = risk.position_size(eq, float(bar["close"]), float(bar["atr"]), float(bar["stop_mult"]))
                if qty > 0:
                    fill = float(bar["close"]) * (1 + side * SLIPPAGE)
                    state["positions"][sym] = {
                        "side": side, "qty": qty, "entry_price": fill,
                        "stop_price": fill - side * stop_dist,
                        "trail_mult": float(bar["trail_mult"]),
                        "entry_time": datetime.now(timezone.utc).isoformat(),
                        "strategy": inst["strategy"],
                    }
                    log(f"AC {sym} {'long' if side == 1 else 'short'} {qty:.6f} @ {fill:.2f} "
                        f"stop {fill - side * stop_dist:.2f}")

    # gunluk zarar limiti
    today = datetime.now(timezone.utc).date().isoformat()
    eq = mark_equity(state, prices)
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = eq
        state["day_blocked"] = False
    if not state["day_blocked"] and eq < state["day_start_equity"] * (1 - risk.cfg.daily_loss_limit):
        log(f"GUNLUK LIMIT: equity {eq:.2f}, tum pozisyonlar kapatiliyor")
        for sym in list(state["positions"]):
            close_position(state, sym, prices.get(sym, state["positions"][sym]["entry_price"]), "daily_limit")
        state["day_blocked"] = True
        eq = mark_equity(state, prices)

    state["history"].append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "equity": round(eq, 2),
        "prices": {k: round(v, 2) for k, v in prices.items()},
    })
    state["history"] = state["history"][-5000:]
    save_state(state)
    pos_txt = ", ".join(
        f"{s}:{'L' if p['side'] == 1 else 'S'}" for s, p in state["positions"].items()
    ) or "yok"
    log(f"Dongu tamam. Equity {eq:,.2f}$  acik pozisyon: {pos_txt}")


def seconds_to_next_4h() -> float:
    now = time.time()
    period = 4 * 3600
    return period - (now % period) + 120  # bar kapanisindan 2 dk sonra


def main():
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    if "--reset" in sys.argv:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        log("Sanal hesap sifirlandi (10.000$)")
        return
    risk = RiskManager(RiskConfig())
    if "--loop" in sys.argv:
        log("Loop modu basladi: her 4 saatlik bar kapanisinda dongu")
        while True:
            try:
                cycle(risk)
            except Exception as e:
                log(f"HATA dongu: {e}")
            time.sleep(seconds_to_next_4h())
    else:
        cycle(risk)


if __name__ == "__main__":
    main()
