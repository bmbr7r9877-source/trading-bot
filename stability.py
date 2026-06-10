"""Varyant istikrar analizi: walk-forward'in tersten okunusu.

walkforward.py her fold'da 'en iyi'yi secip sinar; bu arac ise HER varyanti
TUM fold'larin test donemlerinde kosturur ve fold'lar arasi tutarliligi olcer.
Amac: secim algoritmasinin oynakligindan bagimsiz, "her donemde ayakta kalan"
saglam varyant var mi gormek. Varsa canli konfig ona sabitlenir; yoksa
enstruman cikarilir.

Siralama anahtari: fold'larin kacinda pozitif + en kotu fold getirisi
(once saglamlik, sonra ortalama). Train verisi hic kullanilmaz — burada
secim yapmiyoruz, dayanikliligi olcuyoruz.

Kullanim: .venv/bin/python stability.py [SYMBOL] [tf ...]
Ornek:    .venv/bin/python stability.py ETHUSDT 4h 8h
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

from botlib import data, strategies
from research import run_variant
from walkforward import TRAIN, TEST, STEP, build_variants


def main():
    args = sys.argv[1:]
    symbol = args[0] if args and args[0].endswith("USDT") else "ETHUSDT"
    timeframes = [a for a in args if not a.endswith("USDT")] or ["4h", "8h"]

    print(f"Veri cekiliyor... ({symbol}, {', '.join(timeframes)})")
    raw = {tf: data.fetch_binance(symbol, tf, days=730) for tf in timeframes}
    variants = build_variants(timeframes)
    prepared = {
        i: strategies.REGISTRY[strat](raw[tf], **params)
        for i, (tf, strat, params) in enumerate(variants)
    }

    ref = raw[timeframes[0]]
    t0, t2 = ref.index.min(), ref.index.max()

    # fold sinirlari (walkforward ile ayni)
    folds = []
    k = 0
    while t0 + k * STEP + TRAIN + TEST <= t2 + pd.Timedelta(days=10):
        tr_b = t0 + k * STEP + TRAIN
        folds.append((tr_b, min(tr_b + TEST, t2)))
        k += 1
    print(f"{len(folds)} fold'un TEST donemleri: "
          + ", ".join(f"{a.date()}" for a, _ in folds))

    rows = []
    for i, (tf, strat, params) in enumerate(variants):
        rets, trades = [], 0
        for a, b in folds:
            m = run_variant(symbol, prepared[i], strat, a, b)
            rets.append(m["ret"])
            trades += m["trades"]
        rets_s = pd.Series(rets)
        rows.append({
            "tf": tf, "strategy": strat, "params": str(params),
            "pos_folds": int((rets_s > 0).sum()), "n_folds": len(folds),
            "worst": rets_s.min(), "mean": rets_s.mean(), "total_trades": trades,
            **{f"f{j}": r for j, r in enumerate(rets)},
        })

    res = pd.DataFrame(rows).sort_values(
        ["pos_folds", "worst"], ascending=False)
    pd.set_option("display.width", 220)

    fold_cols = [f"f{j}" for j in range(len(folds))]
    pct = "{:+.1%}".format
    print("\n" + "=" * 110)
    print(f"{symbol}: varyantlarin fold-fold TEST getirileri "
          f"(siralama: pozitif fold sayisi, sonra en kotu fold):")
    print("=" * 110)
    print(res.head(12)[["tf", "strategy", "params", "pos_folds", "worst", "mean",
                        "total_trades"] + fold_cols].to_string(
        index=False, formatters={c: pct for c in fold_cols + ["worst", "mean"]}))

    best = res.iloc[0]
    print(f"\nEn saglam varyant: {best['tf']} {best['strategy']} {best['params']}")
    print(f"  {best['pos_folds']}/{best['n_folds']} fold pozitif, "
          f"en kotu fold {best['worst']:+.1%}, ortalama {best['mean']:+.1%}/90g")
    if best["pos_folds"] < best["n_folds"] - 1 or best["mean"] <= 0:
        print("  YORUM: tum donemlerde ayakta kalan varyant YOK — "
              "enstrumani cikarmak en durust secenek.")


if __name__ == "__main__":
    main()
