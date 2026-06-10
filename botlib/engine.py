"""Portfoy seviyesinde, bar-bar (event-driven) backtest motoru.

Birden fazla enstrumani farkli zaman dilimlerinde ayni anda simule eder:
tum barlar zaman sirasina dizilir, her bar'da sirasiyla stop kontrolu,
cikis sinyali, gunluk zarar limiti ve giris sinyali islenir.
Sinyaller strateji katmaninda 1 bar geriye kaydirildigi icin look-ahead yoktur;
emirler bar acilis fiyatindan, komisyon + slippage dusulerek gerceklesir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .risk import RiskManager


@dataclass
class Instrument:
    symbol: str
    df: pd.DataFrame          # strategies.prepare ciktisi
    strategy: str
    commission: float = 0.001  # tek yon (Binance spot taker ~%0.1)
    slippage: float = 0.0003


@dataclass
class Position:
    symbol: str
    side: int                 # +1 long, -1 short
    qty: float
    entry_price: float
    stop_price: float
    trail_mult: float
    entry_time: pd.Timestamp
    strategy: str


@dataclass
class Trade:
    symbol: str
    strategy: str
    side: int
    qty: float
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    pnl: float
    reason: str


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list = field(default_factory=list)

    def trades_df(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.trades])


class Engine:
    def __init__(self, instruments: list[Instrument], risk: RiskManager,
                 initial_equity: float = 10_000.0):
        self.instruments = {i.symbol: i for i in instruments}
        self.risk = risk
        self.initial_equity = initial_equity

    def run(self) -> BacktestResult:
        events = []
        for sym, inst in self.instruments.items():
            for ts, row in zip(inst.df.index, inst.df.itertuples(index=False)):
                events.append((ts, sym, row))
        events.sort(key=lambda e: e[0])

        cash = self.initial_equity
        positions: dict[str, Position] = {}
        last_price: dict[str, float] = {}
        trades: list[Trade] = []
        equity_points = []
        day = None
        day_start_equity = self.initial_equity
        day_blocked = False

        def mark_equity() -> float:
            unrealized = sum(
                p.side * p.qty * (last_price[p.symbol] - p.entry_price)
                for p in positions.values()
            )
            return cash + unrealized

        def close_position(p: Position, price: float, ts, reason: str):
            nonlocal cash
            inst = self.instruments[p.symbol]
            fill = price * (1 - p.side * inst.slippage)
            fees = (p.entry_price + fill) * p.qty * inst.commission
            pnl = p.side * p.qty * (fill - p.entry_price) - fees
            cash += pnl
            trades.append(Trade(p.symbol, p.strategy, p.side, p.qty, p.entry_time,
                                p.entry_price, ts, fill, pnl, reason))
            del positions[p.symbol]

        for ts, sym, row in events:
            inst = self.instruments[sym]
            last_price[sym] = row.close

            # gun degisimi: limiti sifirla
            d = ts.date()
            if d != day:
                day = d
                day_start_equity = mark_equity()
                day_blocked = False

            p: Optional[Position] = positions.get(sym)

            # 1) stop kontrolu (bar ici high/low ile)
            if p is not None:
                if p.side == 1 and row.low <= p.stop_price:
                    close_position(p, min(row.open, p.stop_price), ts, "stop")
                    p = None
                elif p.side == -1 and row.high >= p.stop_price:
                    close_position(p, max(row.open, p.stop_price), ts, "stop")
                    p = None

            # 2) strateji cikis sinyali (bar acilisinda)
            if p is not None:
                if (p.side == 1 and row.exit_long) or (p.side == -1 and row.exit_short):
                    close_position(p, row.open, ts, "signal")
                    p = None

            # 3) trailing stop guncelle
            if p is not None and p.trail_mult > 0:
                if p.side == 1:
                    p.stop_price = max(p.stop_price, row.close - p.trail_mult * row.atr)
                else:
                    p.stop_price = min(p.stop_price, row.close + p.trail_mult * row.atr)

            # 4) gunluk zarar limiti
            eq = mark_equity()
            if not day_blocked and eq < day_start_equity * (1 - self.risk.cfg.daily_loss_limit):
                for sp in list(positions.values()):
                    close_position(sp, last_price[sp.symbol], ts, "daily_limit")
                day_blocked = True

            # 5) giris
            if not day_blocked and row.entry != 0 and sym not in positions:
                side = int(row.entry)
                open_sides = {s: pos.side for s, pos in positions.items()}
                if self.risk.allow_entry(sym, side, open_sides):
                    eq = mark_equity()
                    qty, stop_dist = self.risk.position_size(eq, row.open, row.atr, row.stop_mult)
                    if qty > 0:
                        fill = row.open * (1 + side * inst.slippage)
                        positions[sym] = Position(
                            symbol=sym, side=side, qty=qty, entry_price=fill,
                            stop_price=fill - side * stop_dist,
                            trail_mult=row.trail_mult, entry_time=ts,
                            strategy=inst.strategy,
                        )

            equity_points.append((ts, mark_equity()))

        # acik pozisyonlari son fiyattan kapat
        final_ts = events[-1][0] if events else pd.Timestamp.now(tz="UTC")
        for p in list(positions.values()):
            close_position(p, last_price[p.symbol], final_ts, "end_of_test")

        eq_series = pd.Series(
            [e for _, e in equity_points],
            index=pd.DatetimeIndex([t for t, _ in equity_points]),
        )
        eq_series = eq_series.groupby(eq_series.index).last()
        return BacktestResult(equity=eq_series, trades=trades)
