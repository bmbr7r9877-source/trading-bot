"""Risk yonetimi: ATR bazli boyutlandirma, sabit %1 risk, korelasyon filtresi,
gunluk zarar limiti. Tweetteki kurallarin birebir karsiligi."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01      # her islemde sermayenin %1'i riske atilir
    max_notional_pct: float = 0.30    # tek pozisyon, sermayenin en fazla %30'u (kaldirac yok)
    daily_loss_limit: float = 0.03    # gun ici %3 kayipta tum pozisyonlar kapanir, gun biter
    max_open_positions: int = 4
    # ayni yondeki "risk-on" pozisyon sayisi siniri (korelasyon filtresi)
    corr_group: tuple = ("SPY", "QQQ", "BTCUSDT", "ETHUSDT", "SOLUSDT")
    max_corr_same_side: int = 2


@dataclass
class RiskManager:
    cfg: RiskConfig = field(default_factory=RiskConfig)

    def position_size(self, equity: float, price: float, atr_value: float, stop_mult: float) -> tuple[float, float]:
        """(miktar, stop_mesafesi) doner. Boyut oyle secilir ki stop yenirse
        kayip = equity * risk_per_trade olur. Volatil gunde kucuk, sakin gunde
        buyuk pozisyon — risk sabit kalir."""
        stop_dist = stop_mult * atr_value
        if stop_dist <= 0 or price <= 0:
            return 0.0, 0.0
        qty = (equity * self.cfg.risk_per_trade) / stop_dist
        max_qty = (equity * self.cfg.max_notional_pct) / price
        return min(qty, max_qty), stop_dist

    def allow_entry(self, symbol: str, side: int, open_positions: dict) -> bool:
        """open_positions: {symbol: side}. Korelasyon + pozisyon sayisi kontrolu."""
        if symbol in open_positions:
            return False
        if len(open_positions) >= self.cfg.max_open_positions:
            return False
        if symbol in self.cfg.corr_group:
            same_side = sum(
                1 for s, sd in open_positions.items()
                if s in self.cfg.corr_group and sd == side
            )
            if same_side >= self.cfg.max_corr_same_side:
                return False
        return True
