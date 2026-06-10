"""Funding rate sinyal arastirmasi: train/test ayrimi ile parametre taramasi.

Hipotez: Binance perp funding orani kalabaligin yonunu gosterir; tarihsel
ortalamadan asiri sapma (rolling z-skor) crowded trade'dir ve ters yonde
islem firsati olabilir (kontra + short tarafta carry).

Metodoloji research.py ile ayni (overfitting'e karsi):
  - 2 yillik veri ikiye bolunur: ilk yil TRAIN, son yil TEST.
  - Tum varyantlar train'de kosturulur, en iyi Sharpe secilir.
  - Karar metrigi secilen varyantin TEST performansidir.
  - Tum varyantlarin test dagilimi da basilir: en iyi train varyanti
    test'te ortalamanin ustunde degilse gurultu fit edilmis demektir.

Veri hizalama (look-ahead yok): funding T aninda (00/08/16 UTC) gerceklesir
ve T'de acilan 8s bar'a yazilir; sinyal o bar'in kapanisinda uretilir ve
bir SONRAKI bar'in acilisinda islenir (strategies._finalize shift'i).

Kullanim: .venv/bin/python funding_research.py
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from botlib import data, strategies
from research import run_variant

SYMBOLS = ("BTCUSDT", "ETHUSDT")


def main():
    print("Veri cekiliyor (8h klines + funding gecmisi)...")
    merged = {}
    for sym in SYMBOLS:
        df = data.fetch_binance(sym, "8h", days=730)
        funding = data.fetch_funding(sym, days=730)
        df = df.copy()
        df["funding"] = funding.reindex(df.index)
        n_miss = df["funding"].isna().sum()
        if n_miss:
            print(f"  uyari: {sym} {n_miss} bar'da funding eslesmedi (atilacak)")
        merged[sym] = df

    ref = merged["BTCUSDT"]
    t0, t2 = ref.index.min(), ref.index.max()
    t1 = t0 + (t2 - t0) / 2
    print(f"TRAIN: {t0.date()} -> {t1.date()}   TEST: {t1.date()} -> {t2.date()}")

    # baglam: funding dagilimi
    for sym in SYMBOLS:
        f = merged[sym]["funding"].dropna()
        print(f"  {sym} funding: medyan {f.median():+.4%}  p5 {f.quantile(0.05):+.4%}  "
              f"p95 {f.quantile(0.95):+.4%}  yillik medyan carry ~{f.median() * 3 * 365:+.1%}")
    print()

    variants = []
    for sym in SYMBOLS:
        for z_n in (30, 90, 180):            # 10 / 30 / 60 gun
            for entry_z in (1.5, 2.0, 2.5):
                for exit_z in (0.0, 0.5):
                    for short in (True, False):
                        variants.append({
                            "symbol": sym,
                            "params": {"z_n": z_n, "entry_z": entry_z,
                                       "exit_z": exit_z, "allow_short": short},
                        })

    rows = []
    for v in variants:
        prepared = strategies.funding_extreme(merged[v["symbol"]], **v["params"])
        tr = run_variant(v["symbol"], prepared, "funding_extreme", t0, t1)
        te = run_variant(v["symbol"], prepared, "funding_extreme", t1, t2)
        rows.append({
            "symbol": v["symbol"], "params": str(v["params"]),
            "train_ret": tr["ret"], "train_sharpe": tr["sharpe"], "train_n": tr["trades"],
            "test_ret": te["ret"], "test_sharpe": te["sharpe"],
            "test_dd": te["max_dd"], "test_n": te["trades"],
        })

    res = pd.DataFrame(rows)
    pd.set_option("display.width", 220)

    print("=" * 110)
    print("TRAIN'de en iyi 10 (Sharpe, min 12 train islemi) — ve TEST sonuclari:")
    print("=" * 110)
    eligible = res[res.train_n >= 12]
    top = (eligible if len(eligible) else res).sort_values("train_sharpe", ascending=False).head(10)
    cols = ["symbol", "params", "train_ret", "train_sharpe", "train_n",
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
    print(f"  test'te karda olan varyant: {(res.test_ret > 0).sum()}/{len(res)}")

    bh = {}
    for sym in SYMBOLS:
        test_df = merged[sym][merged[sym].index >= t1]
        bh[sym] = test_df.close.iloc[-1] / test_df.close.iloc[0] - 1
    print(f"  TEST donemi buy&hold: BTC {bh['BTCUSDT']:+.1%}, ETH {bh['ETHUSDT']:+.1%}")

    res.to_csv("results/funding_grid.csv", index=False)
    print("\nTum grid: results/funding_grid.csv")


if __name__ == "__main__":
    main()
