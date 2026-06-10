"""Tarihsel OHLCV verisi: Binance (kripto) ve yfinance (ABD hisse/endeks).

Tum DataFrame'ler ayni formatta doner:
  index: UTC tz-aware DatetimeIndex (bar acilis zamani)
  kolonlar: open, high, low, close, volume
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Ana endpoint + yedek: data-api.binance.vision sadece public piyasa verisi
# sunan resmi ayna; api.binance.com'un eristiremedigi yerlerden (orn. GitHub
# Actions'in ABD sunuculari, HTTP 451) calisir.
BINANCE_URLS = [
    "https://api.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

_INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def fetch_binance(symbol: str, interval: str, days: int, use_cache: bool = True) -> pd.DataFrame:
    """Binance public API'den klines ceker, sayfalayarak. API anahtari gerekmez."""
    cache_file = CACHE_DIR / f"binance_{symbol}_{interval}_{days}d.csv"
    if use_cache and cache_file.exists() and time.time() - cache_file.stat().st_mtime < 6 * 3600:
        return _read_cache(cache_file)

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        batch = None
        last_err = None
        for url in BINANCE_URLS:
            try:
                resp = requests.get(
                    url,
                    params={"symbol": symbol, "interval": interval,
                            "startTime": cursor, "limit": 1000},
                    timeout=30,
                )
                resp.raise_for_status()
                batch = resp.json()
                break
            except requests.RequestException as e:
                last_err = e
        if batch is None:
            raise last_err
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + _INTERVAL_MS[interval]
        time.sleep(0.15)  # rate limit nezaketi

    df = pd.DataFrame(
        rows, columns=["open_time", "open", "high", "low", "close", "volume",
                       "close_time", "qv", "trades", "tbb", "tbq", "ignore"],
    )
    df = df[["open_time", "open", "high", "low", "close", "volume"]].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    # son bar henuz kapanmamis olabilir, at
    df = df.iloc[:-1]
    df.to_csv(cache_file)
    return df


def fetch_funding(symbol: str, days: int, use_cache: bool = True) -> pd.Series:
    """Binance USDT-M perp funding rate gecmisi (8 saatte bir: 00/08/16 UTC).

    Index: funding'in gerceklestigi zaman (UTC), deger: o periyodun orani
    (orn. 0.0001 = %0.01). Public endpoint, API anahtari gerekmez.
    """
    cache_file = CACHE_DIR / f"funding_{symbol}_{days}d.csv"
    if use_cache and cache_file.exists() and time.time() - cache_file.stat().st_mtime < 6 * 3600:
        df = _read_cache(cache_file)
        return df["fundingRate"]

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": symbol, "startTime": cursor, "limit": 1000},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1]["fundingTime"] + 1
        time.sleep(0.15)

    df = pd.DataFrame(rows)[["fundingTime", "fundingRate"]]
    df["fundingRate"] = df["fundingRate"].astype(float)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    # funding zamanlari tam 00/08/16'da olmali; ms sapmalarini yuvarla
    df["fundingTime"] = df["fundingTime"].dt.round("1h")
    df = df.set_index("fundingTime").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    return df["fundingRate"]


def fetch_stock(symbol: str, interval: str = "15m", period: str = "60d", use_cache: bool = True) -> pd.DataFrame:
    """yfinance'tan hisse/ETF verisi. 15m veri en fazla son ~60 gun ile sinirli."""
    cache_file = CACHE_DIR / f"yf_{symbol}_{interval}_{period}.csv"
    if use_cache and cache_file.exists() and time.time() - cache_file.stat().st_mtime < 6 * 3600:
        return _read_cache(cache_file)

    import yfinance as yf

    hist = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if hist.empty:
        raise RuntimeError(f"yfinance bos veri dondu: {symbol} {interval} {period}")
    df = hist.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index = df.index.tz_convert("UTC")
    df.index.name = "open_time"
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.to_csv(cache_file)
    return df


def _read_cache(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df
