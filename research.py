"""Strateji arastirmasi: train/test ayrimi ile parametre taramasi.

Metodoloji (overfitting'e karsi):
  - 2 yillik veri ikiye bolunur: ilk yil TRAIN, son yil TEST.
  - Tum varyantlar train'de kosturulur, en iyi Sharpe secilir.
  - Secilen varyantin TEST performansi raporlanir — karar metrigi budur.
  - Tum varyantlarin test sonuclari da basilir ki dagilimi gorelim
    (en iyi train varyanti test'te de ortalamanin ustundeyse sinyal gercek,
    degilse gurultuyu fit etmisiz demektir).

Kullanim: .venv/bin/python research.py [tf ...]   (varsayilan: 1h 4h)
Ornek:    .venv/bin/python research.py 4h 8h 12h 1d
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from botlib import data, strategies
from botlib.engine import Engine, Instrument
from botlib.risk import RiskConfig, RiskManager

INITIAL = 10_000.0

# Taranacak coinler. Likit, yuksek hacimli major'lar — ilk arguman virgullu
# liste verilirse onu kullanir: .venv/bin/python research.py BTCUSDT,SOLUSDT 4h 8h
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT")


def quick_metrics(equity: pd.Series, trades: pd.DataFrame) -> dict:
    ret = equity.iloc[-1] / INITIAL - 1
    daily = equity.resample("1D").last().dropna().pct_change().dropna()
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if len(daily) > 1 and daily.std() > 0 else 0.0
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min()
    return {"ret": ret, "sharpe": sharpe, "max_dd": max_dd, "trades": len(trades)}


def run_variant(symbol: str, df_prepared: pd.DataFrame, strategy: str,
                start, end) -> dict:
    window = df_prepared[(df_prepared.index >= start) & (df_prepared.index < end)]
    if len(window) < 50:
        return {"ret": 0.0, "sharpe": 0.0, "max_dd": 0.0, "trades": 0}
    engine = Engine([Instrument(symbol, window, strategy)], RiskManager(RiskConfig()), INITIAL)
    res = engine.run()
    return quick_metrics(res.equity, res.trades_df())


def main():
    args = sys.argv[1:]
    # ilk arguman virgul iceriyorsa coin listesi, kalani zaman dilimleri
    if args and "," in args[0]:
        symbols = tuple(args[0].split(","))
        args = args[1:]
    else:
        symbols = DEFAULT_SYMBOLS
    timeframes = args or ["4h", "8h"]
    print(f"Veri cekiliyor... (coinler: {', '.join(symbols)} | zaman dilimleri: {', '.join(timeframes)})")
    raw = {
        (sym, tf): data.fetch_binance(sym, tf, days=730)
        for sym in symbols for tf in timeframes
    }

    ref = raw[("BTCUSDT", timeframes[0])]
    t0 = ref.index.min()
    t2 = ref.index.max()
    t1 = t0 + (t2 - t0) / 2  # yarisi train, yarisi test
    print(f"TRAIN: {t0.date()} -> {t1.date()}   TEST: {t1.date()} -> {t2.date()}\n")

    variants = []
    for sym in symbols:
        for tf in timeframes:
            for entry_n in (24, 48, 96):
                for short in (True, False):
                    variants.append({
                        "symbol": sym, "tf": tf, "strategy": "momentum_breakout",
                        "params": {"entry_n": entry_n, "exit_n": entry_n // 2, "allow_short": short},
                    })
            for fast, slow in ((20, 100), (50, 200)):
                for short in (True, False):
                    variants.append({
                        "symbol": sym, "tf": tf, "strategy": "trend_following",
                        "params": {"fast": fast, "slow": slow, "allow_short": short},
                    })

    rows = []
    for v in variants:
        df = raw[(v["symbol"], v["tf"])]
        prepared = strategies.REGISTRY[v["strategy"]](df, **v["params"])
        tr = run_variant(v["symbol"], prepared, v["strategy"], t0, t1)
        te = run_variant(v["symbol"], prepared, v["strategy"], t1, t2)
        rows.append({
            "symbol": v["symbol"], "tf": v["tf"], "strategy": v["strategy"],
            "params": str(v["params"]),
            "train_ret": tr["ret"], "train_sharpe": tr["sharpe"], "train_n": tr["trades"],
            "test_ret": te["ret"], "test_sharpe": te["sharpe"],
            "test_dd": te["max_dd"], "test_n": te["trades"],
        })

    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)

    print("=" * 100)
    print("TRAIN'de en iyi 10 (Sharpe) — ve ayni varyantlarin TEST sonuclari:")
    print("=" * 100)
    top = res.sort_values("train_sharpe", ascending=False).head(10)
    cols = ["symbol", "tf", "strategy", "params", "train_ret", "train_sharpe",
            "test_ret", "test_sharpe", "test_dd", "test_n"]
    print(top[cols].to_string(index=False, formatters={
        "train_ret": "{:+.1%}".format, "test_ret": "{:+.1%}".format,
        "train_sharpe": "{:.2f}".format, "test_sharpe": "{:.2f}".format,
        "test_dd": "{:.1%}".format,
    }))

    print()
    print("Karsilastirma: tum varyantlarin TEST getiri dagilimi")
    print(f"  medyan: {res.test_ret.median():+.1%}   "
          f"en iyi: {res.test_ret.max():+.1%}   en kotu: {res.test_ret.min():+.1%}")
    n_pos = (res.test_ret > 0).sum()
    print(f"  test'te karda olan varyant: {n_pos}/{len(res)}")

    bh = {}
    for (sym, tf), df in raw.items():
        if tf == timeframes[0]:
            test_df = df[df.index >= t1]
            bh[sym] = test_df.close.iloc[-1] / test_df.close.iloc[0] - 1
    print("  referans TEST donemi buy&hold: " +
          ", ".join(f"{s.replace('USDT','')} {bh[s]:+.1%}" for s in symbols))

    # Coin basina secim: en yuksek train Sharpe + min 12 train islemi olan varyant.
    # Bu, paper_trader'a hangi konfigi ekleyecegimizin kararidir.
    print()
    print("=" * 100)
    print("COIN BASINA SECIM (train Sharpe + min 12 train islemi) ve out-of-sample TEST:")
    print("=" * 100)
    sel_cols = ["symbol", "tf", "strategy", "params", "train_sharpe", "train_n",
                "test_ret", "test_sharpe", "test_dd", "test_n"]
    picks = []
    for sym in symbols:
        elig = res[(res.symbol == sym) & (res.train_n >= 12)]
        pool = elig if len(elig) else res[res.symbol == sym]
        picks.append(pool.sort_values("train_sharpe", ascending=False).iloc[0])
    picks_df = pd.DataFrame(picks)
    print(picks_df[sel_cols].to_string(index=False, formatters={
        "train_sharpe": "{:.2f}".format, "test_sharpe": "{:.2f}".format,
        "test_ret": "{:+.1%}".format, "test_dd": "{:.1%}".format,
    }))
    n_ok = (picks_df.test_ret > 0).sum()
    print(f"\n  Secilenlerden TEST'te karda olan: {n_ok}/{len(picks_df)} "
          f"(sadece bunlar paper'a aday)")

    res.to_csv("results/research_grid.csv", index=False)
    print("\nTum grid: results/research_grid.csv")


if __name__ == "__main__":
    main()
