"""Uc strateji. Hepsi ayni arayuzu kullanir:

prepare(df) -> df'e su kolonlari ekler:
  entry      : +1 long, -1 short, 0 yok (bir onceki bar kapanisinda uretilen sinyal,
               motor bu bar'in ACILISINDA islem yapar -> look-ahead yok)
  exit_long  : bool, acik long pozisyonu kapat
  exit_short : bool, acik short pozisyonu kapat
  atr        : pozisyon boyutlandirma ve stop mesafesi icin
  stop_mult  : stop mesafesi = stop_mult * atr
  trail_mult : >0 ise motor stop'u bu mesafede takip ettirir (trailing stop)
"""
from __future__ import annotations

import pandas as pd

from . import indicators as ta


def _finalize(df: pd.DataFrame, entry, exit_long, exit_short, atr_n, stop_mult, trail_mult=0.0):
    out = df.copy()
    out["atr"] = ta.atr(df, atr_n)
    # sinyaller bar kapanisinda olusur, bir sonraki bar'da islenir
    out["entry"] = entry.shift(1, fill_value=0).astype(int)
    out["exit_long"] = exit_long.shift(1, fill_value=False).astype(bool)
    out["exit_short"] = exit_short.shift(1, fill_value=False).astype(bool)
    # canli (paper) mod icin kaydirilmamis hali: son kapanan barin sinyali = simdi islenecek emir
    out["entry_now"] = entry.astype(int)
    out["exit_long_now"] = exit_long.astype(bool)
    out["exit_short_now"] = exit_short.astype(bool)
    out["stop_mult"] = stop_mult
    out["trail_mult"] = trail_mult
    return out.dropna(subset=["atr"])


def mean_reversion(df: pd.DataFrame, bb_n=20, bb_k=2.0, rsi_n=2, rsi_low=10, rsi_high=90,
                   atr_n=14, stop_mult=2.5) -> pd.DataFrame:
    """15dk endeks ETF'leri icin: Bollinger alt bandi + asiri satim RSI -> long,
    ust bant + asiri alim -> short. Cikis: orta banda (SMA) donus."""
    lower, mid, upper = ta.bollinger(df["close"], bb_n, bb_k)
    r = ta.rsi(df["close"], rsi_n)

    entry = pd.Series(0, index=df.index)
    entry[(df["close"] < lower) & (r < rsi_low)] = 1
    entry[(df["close"] > upper) & (r > rsi_high)] = -1

    exit_long = df["close"] >= mid
    exit_short = df["close"] <= mid
    return _finalize(df, entry, exit_long, exit_short, atr_n, stop_mult)


def momentum_breakout(df: pd.DataFrame, entry_n=48, exit_n=24, atr_n=14, stop_mult=2.0,
                      allow_short=True, regime_n=200) -> pd.DataFrame:
    """1s kripto icin Donchian kirilimi: onceki entry_n bar'in zirvesini kapanisla
    kirarsa long. Cikis: exit_n bar'in dibinin altina kapanis.
    Rejim filtresi: long kirilimlar sadece EMA(regime_n) ustunde, shortlar altinda
    alinir — yatay piyasadaki yanlis kirilimlari (whipsaw) eler."""
    e_low, e_high = ta.donchian(df, entry_n)
    x_low, x_high = ta.donchian(df, exit_n)
    regime = ta.ema(df["close"], regime_n)

    entry = pd.Series(0, index=df.index)
    entry[(df["close"] > e_high) & (df["close"] > regime)] = 1
    if allow_short:
        entry[(df["close"] < e_low) & (df["close"] < regime)] = -1

    exit_long = df["close"] < x_low
    exit_short = df["close"] > x_high
    return _finalize(df, entry, exit_long, exit_short, atr_n, stop_mult)


def trend_following(df: pd.DataFrame, fast=50, slow=200, atr_n=14, stop_mult=3.0,
                    trail_mult=3.0, allow_short=True) -> pd.DataFrame:
    """4s yavas katman: EMA(50) > EMA(200) ve fiyat hizli EMA ustundeyken long,
    chandelier tarzi 3*ATR trailing stop ile trende binip kalir."""
    f, s = ta.ema(df["close"], fast), ta.ema(df["close"], slow)
    up = (f > s) & (f.shift(1) <= s.shift(1))
    down = (f < s) & (f.shift(1) >= s.shift(1))

    entry = pd.Series(0, index=df.index)
    entry[up & (df["close"] > f)] = 1
    if allow_short:
        entry[down & (df["close"] < f)] = -1

    # trend donusu de cikis sayilir; asil cikis genelde trailing stop'tan gelir
    exit_long = f < s
    exit_short = f > s
    return _finalize(df, entry, exit_long, exit_short, atr_n, stop_mult, trail_mult)


REGISTRY = {
    "mean_reversion": mean_reversion,
    "momentum_breakout": momentum_breakout,
    "trend_following": trend_following,
}
