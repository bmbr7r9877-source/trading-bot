"""Backtest performans metrikleri."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(equity: pd.Series, trades: pd.DataFrame, initial: float) -> dict:
    total_return = equity.iloc[-1] / initial - 1
    daily = equity.resample("1D").last().dropna().pct_change().dropna()

    n_days = max((equity.index[-1] - equity.index[0]).days, 1)
    cagr = (equity.iloc[-1] / initial) ** (365 / n_days) - 1

    sharpe = float("nan")
    if len(daily) > 1 and daily.std() > 0:
        sharpe = daily.mean() / daily.std() * np.sqrt(365)

    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min()

    out = {
        "Donem (gun)": n_days,
        "Toplam getiri": f"{total_return:+.2%}",
        "Yillik getiri (CAGR)": f"{cagr:+.2%}",
        "Sharpe (gunluk, yilliklandirilmis)": f"{sharpe:.2f}",
        "Maks. dusus (drawdown)": f"{max_dd:.2%}",
        "Islem sayisi": len(trades),
    }
    if len(trades):
        wins = trades[trades.pnl > 0]
        losses = trades[trades.pnl <= 0]
        pf = wins.pnl.sum() / abs(losses.pnl.sum()) if len(losses) and losses.pnl.sum() != 0 else float("inf")
        out.update({
            "Kazanma orani": f"{len(wins) / len(trades):.1%}",
            "Profit factor": f"{pf:.2f}",
            "Ort. islem PnL": f"{trades.pnl.mean():+.2f} USD",
            "En kotu islem": f"{trades.pnl.min():+.2f} USD",
        })
    return out


def per_symbol(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby(["symbol", "strategy"])
    res = g.agg(
        islem=("pnl", "size"),
        toplam_pnl=("pnl", "sum"),
        kazanma=("pnl", lambda s: f"{(s > 0).mean():.0%}"),
        ort_pnl=("pnl", "mean"),
    )
    return res.round(2)
