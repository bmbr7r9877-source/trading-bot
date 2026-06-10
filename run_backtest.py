"""Backtest calistirici.

Iki kosum yapar:
  1) Portfoy (son ~60 gun): SPY + QQQ 15m mean reversion, BTC 1h momentum,
     ETH 4h trend following — hepsi ayni anda, ortak risk yonetimiyle.
     (60 gun siniri yfinance'in 15dk veri limitinden gelir.)
  2) Kripto-only (2 yil): BTC 1h momentum + ETH 4h trend — stratejinin uzun
     vadede ayakta kalip kalmadigini gormek icin.

Kullanim: .venv/bin/python run_backtest.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from botlib import data, strategies
from botlib.engine import Engine, Instrument
from botlib.metrics import per_symbol, summarize
from botlib.risk import RiskConfig, RiskManager

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

INITIAL_EQUITY = 10_000.0


def run(name: str, instruments: list[Instrument]):
    print(f"\n{'=' * 60}\n  {name}\n{'=' * 60}")
    engine = Engine(instruments, RiskManager(RiskConfig()), INITIAL_EQUITY)
    result = engine.run()
    trades = result.trades_df()

    for k, v in summarize(result.equity, trades, INITIAL_EQUITY).items():
        print(f"  {k:<38} {v}")
    if not trades.empty:
        print("\n  Enstruman bazinda:")
        print(per_symbol(trades).to_string().replace("\n", "\n  "))

    slug = name.lower().replace(" ", "_")
    trades.to_csv(RESULTS / f"{slug}_trades.csv", index=False)
    result.equity.rename("equity").to_csv(RESULTS / f"{slug}_equity.csv")
    print(f"\n  CSV: results/{slug}_trades.csv, results/{slug}_equity.csv")
    return result


def main():
    print("Veri cekiliyor...")
    btc_8h = data.fetch_binance("BTCUSDT", "8h", days=730)
    eth_4h = data.fetch_binance("ETHUSDT", "4h", days=730)
    spy = data.fetch_stock("SPY", "15m", "60d")
    qqq = data.fetch_stock("QQQ", "15m", "60d")
    print(f"  BTC 8h: {len(btc_8h)} bar | ETH 4h: {len(eth_4h)} bar | "
          f"SPY 15m: {len(spy)} bar | QQQ 15m: {len(qqq)} bar")

    # Kripto konfigurasyonu research.py taramasindan: train Sharpe siralamasi +
    # minimum 12 train islemi sarti (istatistiksel anlamlilik icin; 1d gibi
    # cok yavas dilimler test yilinda 0-2 islem yapip dogrulanamiyor).
    # paper_trader.py ile ayni konfigurasyon.
    # indikatorler tum veride hesaplanir (warmup icin), sonra pencere kesilir
    btc_p = strategies.trend_following(btc_8h, fast=20, slow=100)
    eth_p = strategies.momentum_breakout(eth_4h, entry_n=24, exit_n=12, allow_short=False)
    spy_p = strategies.mean_reversion(spy)
    qqq_p = strategies.mean_reversion(qqq)

    cutoff = spy_p.index.min()  # hisse verisinin basladigi an = ortak pencere

    run("Portfoy 60g", [
        Instrument("SPY", spy_p, "mean_reversion", commission=0.0002, slippage=0.0001),
        Instrument("QQQ", qqq_p, "mean_reversion", commission=0.0002, slippage=0.0001),
        Instrument("BTCUSDT", btc_p[btc_p.index >= cutoff], "trend_following"),
        Instrument("ETHUSDT", eth_p[eth_p.index >= cutoff], "momentum_breakout"),
    ])

    run("Kripto 2y", [
        Instrument("BTCUSDT", btc_p, "trend_following"),
        Instrument("ETHUSDT", eth_p, "momentum_breakout"),
    ])


if __name__ == "__main__":
    main()
