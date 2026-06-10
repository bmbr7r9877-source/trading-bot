# trading-bot

Çoklu enstrüman, çoklu zaman dilimi algoritmik trading botu. Şu an **backtest
aşamasında** — gerçek para bağlanmadan önce stratejilerin geçmiş veride kendini
kanıtlaması gerekiyor.

## Mimari

```
botlib/
├── data.py         # Binance public API (kripto) + yfinance (ABD hisse) veri çekme, cache'li
├── indicators.py   # EMA, RSI, ATR, Bollinger, Donchian
├── strategies.py   # 3 strateji: mean reversion (15m), momentum breakout (1h), trend following (4h)
├── risk.py         # ATR bazlı boyutlandırma, %1 sabit risk, korelasyon filtresi, günlük zarar limiti
├── engine.py       # Bar-bar portföy simülasyonu (komisyon + slippage dahil, look-ahead yok)
└── metrics.py      # Getiri, Sharpe, max drawdown, win rate, profit factor
run_backtest.py     # İki koşum: 60 günlük portföy + 2 yıllık kripto-only
```

## Stratejiler

| Strateji | Enstrüman | Zaman dilimi | Mantık |
|---|---|---|---|
| Mean reversion | SPY, QQQ | 15 dk | Bollinger alt bant + RSI(2) aşırı satım → long; orta banda dönüşte çık |
| Momentum breakout | ETH | 4 saat | Donchian(24) kırılımı, EMA(200) rejim filtresi, long-only; Donchian(12) karşı kırılımda çık |
| Trend following | BTC | 8 saat | EMA(20)/EMA(100) kesişimi; 3×ATR trailing stop |

Kripto konfigürasyonu `research.py` taramasından geliyor: 1h/4h/8h/12h/1d
dilimlerinde 80 varyant, ilk yıl TRAIN / son yıl TEST ayrımıyla. Seçim kuralı:
en yüksek train Sharpe + en az 12 train işlemi (1d gibi çok yavaş dilimler
test yılında 0-2 işlem yapıp doğrulanamadığı için elendi; 1h ise gürültüden
komisyona yeniliyor — tatlı nokta 4h-8h çıktı).

## Risk kuralları (istisnasız)

- Her işlemde sermayenin **%1**'i riske atılır; pozisyon boyutu ATR'ye göre ayarlanır
  (volatil günde küçük, sakin günde büyük pozisyon — risk sabit kalır)
- Tek pozisyon sermayenin en fazla %30'u (kaldıraç yok)
- Günlük **%3** zarar limitinde tüm pozisyonlar kapanır, gün biter
- Korelasyon filtresi: risk-on grupta (SPY/QQQ/BTC/ETH) aynı yönde en fazla 2 pozisyon

## Kullanım

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_backtest.py              # backtest (sonuçlar results/ altında)
.venv/bin/python research.py 4h 8h 12h 1d     # parametre/zaman dilimi taraması
```

## Paper trading: 7/24 GitHub Actions'ta

Bot bilgisayara bağlı değil: `.github/workflows/paper.yml` her 4 saatte bir
GitHub'ın sunucusunda `paper_trader.py`'ı koşturur ve `paper/state.json`'u
repo'ya commit'ler. Gerçek Binance fiyatları (US sunucular için
`data-api.binance.vision` yedeği), sanal para, API anahtarı gerekmez.
Elle tetiklemek için: GitHub → Actions → paper-trading → Run workflow.

İstersen yerelde de çalışır:

```bash
.venv/bin/python paper_trader.py            # tek döngü
.venv/bin/python paper_trader.py --reset    # sanal hesabı 10.000$'a sıfırla
.venv/bin/python dashboard.py               # yerel panel: http://localhost:8742
```

## Günlük rapor + telefon bildirimi (report.py)

Her döngüde `report.py` okunabilir bir özet üretip `paper/report.txt`'e yazar
(bakiye, günlük/haftalık getiri, açık pozisyonlar, son 24s işlemler). Bu dosya
commit'lenir; sıfır kurulumla GitHub'dan ve telefondan okunabilir.

**Gerçek push bildirimi (opsiyonel, ücretsiz, hesapsız — ntfy.sh):**
1. Telefona **ntfy** uygulamasını kur (App Store / Play Store).
2. Uygulamada tahmin edilmesi zor bir konu (topic) adına abone ol,
   örn. `nirengi-bot-7h3k9x`.
3. GitHub → repo → Settings → Secrets and variables → Actions → New secret:
   isim `NTFY_TOPIC`, değer o konu adı (`nirengi-bot-7h3k9x`).

Artık sabah (07:xx TR) ve akşam (19:xx TR) döngülerinde telefonuna push düşer.
Konu adı gizli kaldığı sürece sadece sen görürsün. Yerelde denemek için:
`NTFY_TOPIC=... .venv/bin/python report.py --force`.

## iPhone uygulaması (ios/BotPanel)

SwiftUI izleme uygulaması: sermaye eğrisi (Swift Charts), açık pozisyonlar,
işlem geçmişi. Veriyi GitHub'daki `paper/state.json`'dan okur, 5 dk'da bir
ve her açılışta yeniler; pull-to-refresh var.

Kurulum: `ios/BotPanel.xcodeproj`'u Xcode'da aç → Signing'de kendi Team'ini
seç → iPhone'unu bağla → Run. Veri adresi uygulamanın Ayarlar (⚙) ekranından
değiştirilebilir.

## Mevcut durum (2026-06-10 itibarıyla, dürüst tablo)

- Kripto 2y backtest: **+27.7%**, Sharpe 1.10, maks düşüş -9.4%, 63 işlem
  (aynı dönemde BTC buy&hold -11.8%, ETH -55.7%)
- Dikkat: 2 yıllık koşumun ilk yılı parametre seçiminde kullanıldı (in-sample).
  Saf out-of-sample sonuç (research TEST yılı, piyasa -%40 düşerken):
  BTC 8h trend **+6.9%**, ETH 4h momentum **+4.7%** — gerçekçi beklenti bu.
- Paper trading canlıda: bot her 4 saatte gerçek fiyatlarla karar veriyor,
  panel http://localhost:8742
- Zayıf halka hâlâ hisse mean reversion (QQQ), research'ten geçmedi;
  paper trading'e dahil edilmedi.

## Yol haritası

- [x] Veri katmanı + 3 strateji + risk yönetimi + backtest motoru
- [x] Kripto parametre araştırması (research.py, train/test, 1h→4h/8h'e geçiş)
- [x] Paper trading (sanal para, gerçek fiyat) + yerel panel
- [ ] Hisse mean reversion araştırması (QQQ zarar ediyor) ya da hisseleri şimdilik çıkar
- [ ] Walk-forward doğrulama (tek train/test yerine kayan pencereler)
- [x] Günlük rapor: sabah/akşam bot performansı bildirimi (report.py + ntfy)
- [ ] Canlı (ancak paper'da en az 1-2 ay tutarlı sonuçtan sonra, küçük sermayeyle)

## Uyarı

Bu bir araştırma projesidir, yatırım tavsiyesi değildir. Backtest sonuçları
gelecek getiriyi garanti etmez; canlı sonuçlar slippage, gecikme ve değişen
piyasa rejimleri yüzünden her zaman daha kötüdür.
