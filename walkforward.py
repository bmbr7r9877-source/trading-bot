"""Walk-forward dogrulama: tek train/test bolmesi yerine kayan pencereler.

Her pencerede: onceki 365 gunde (TRAIN) en iyi varyanti sec (test verisine
bakmadan), sonraki 90 gunde (TEST) kostur. Pencereyi 90 gun kaydir, tekrarla.
Tum TEST parcalari dikilerek "hic gorulmemis veride" birlesik sonuc cikar.
Bu, "ilk yilda iyi olan ikinci yilda da iyiydi" iddiasini 4 ayri donemde sinar
— overfitting'in en saglam panzehiri.

Kullanim: .venv/bin/python walkforward.py [tf ...]   (varsayilan: 4h 8h)
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

from botlib import data, strategies
from research import INITIAL, run_variant

TRAIN = pd.Timedelta(days=365)
TEST = pd.Timedelta(days=90)
STEP = pd.Timedelta(days=90)
MIN_TRAIN_TRADES = 8


def build_variants(timeframes):
    out = []
    for tf in timeframes:
        for entry_n in (24, 48, 96):
            for short in (True, False):
                out.append((tf, "momentum_breakout",
                            {"entry_n": entry_n, "exit_n": entry_n // 2, "allow_short": short}))
        for fast, slow in ((20, 100), (50, 200)):
            for short in (True, False):
                out.append((tf, "trend_following",
                            {"fast": fast, "slow": slow, "allow_short": short}))
    return out


def main():
    timeframes = sys.argv[1:] or ["4h", "8h"]
    symbols = ("BTCUSDT", "ETHUSDT")
    print(f"Veri cekiliyor... (zaman dilimleri: {', '.join(timeframes)})")
    raw = {(s, tf): data.fetch_binance(s, tf, days=730) for s in symbols for tf in timeframes}

    variants = build_variants(timeframes)
    # indikatorler tum seride hesaplanir (warmup), pencereler sonra kesilir
    prepared = {
        (sym, i): strategies.REGISTRY[strat](raw[(sym, tf)], **params)
        for sym in symbols
        for i, (tf, strat, params) in enumerate(variants)
    }

    ref = raw[(symbols[0], timeframes[0])]
    t0, t2 = ref.index.min(), ref.index.max()

    stitched = {}
    for sym in symbols:
        print(f"\n{sym} — fold'lar (TRAIN 365g secer, TEST 90g sinar):")
        equity_mult = 1.0
        k = 0
        while t0 + k * STEP + TRAIN + TEST <= t2 + pd.Timedelta(days=10):
            tr_a = t0 + k * STEP
            tr_b = tr_a + TRAIN
            te_b = min(tr_b + TEST, t2)
            best, best_sharpe = None, -99.0
            for i, (tf, strat, params) in enumerate(variants):
                m = run_variant(sym, prepared[(sym, i)], strat, tr_a, tr_b)
                if m["trades"] >= MIN_TRAIN_TRADES and m["sharpe"] > best_sharpe:
                    best, best_sharpe = i, m["sharpe"]
            if best is None:
                print(f"  fold {k}: yeterli islem ureten varyant yok, atlandi")
                k += 1
                continue
            tf, strat, params = variants[best]
            te = run_variant(sym, prepared[(sym, best)], strat, tr_b, te_b)
            equity_mult *= 1 + te["ret"]
            print(f"  fold {k}  {tr_b.date()}->{te_b.date()}  secim: {tf} {strat} {params}")
            print(f"          train Sharpe {best_sharpe:.2f} -> TEST {te['ret']:+.1%} ({te['trades']} islem)")
            k += 1
        stitched[sym] = equity_mult - 1

    print("\n" + "=" * 64)
    print("DIKISLI OUT-OF-SAMPLE SONUC (sadece hic gorulmemis donemler):")
    for sym, r in stitched.items():
        # ayni test donemlerinin buy&hold karsiligi (t0+365 -> t2)
        px = raw[(sym, timeframes[0])]["close"]
        bh_win = px[px.index >= t0 + TRAIN]
        bh = bh_win.iloc[-1] / bh_win.iloc[0] - 1
        print(f"  {sym}: bot {r:+.1%}   (ayni donem buy&hold {bh:+.1%})")
    combo = sum(stitched.values()) / len(stitched)
    print(f"  Esit agirlikli portfoy: {combo:+.1%}")


if __name__ == "__main__":
    main()
