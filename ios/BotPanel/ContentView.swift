import Charts
import SwiftUI

struct ContentView: View {
    @StateObject private var loader = StateLoader()
    @State private var showSettings = false
    private let refresh = Timer.publish(every: 300, on: .main, in: .common).autoconnect()

    private let initialEquity = 10_000.0

    var body: some View {
        NavigationStack {
            List {
                if let state = loader.state {
                    summarySection(state)
                    chartSection(state)
                    positionsSection(state)
                    tradesSection(state)
                } else if let error = loader.errorMessage {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Section {
                        HStack {
                            ProgressView()
                            Text("Yükleniyor…").foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Trading Bot")
            .toolbar {
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "gearshape")
                }
            }
            .sheet(isPresented: $showSettings) { settingsSheet }
            .refreshable { await loader.load() }
            .onReceive(refresh) { _ in Task { await loader.load() } }
            .task { await loader.load() }
        }
    }

    private func summarySection(_ state: BotState) -> some View {
        let ret = state.equity / initialEquity - 1
        return Section {
            VStack(alignment: .leading, spacing: 6) {
                Text(state.equity, format: .currency(code: "USD"))
                    .font(.system(size: 34, weight: .semibold, design: .rounded))
                    .foregroundStyle(ret >= 0 ? .green : .red)
                Text("\(ret >= 0 ? "+" : "")\(ret * 100, specifier: "%.2f")%  ·  sanal para, gerçek fiyatlar")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text("Son güncelleme: \(shortDate(state.lastUpdate)) UTC")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            .padding(.vertical, 4)
        }
    }

    private func chartSection(_ state: BotState) -> some View {
        Section("Sermaye eğrisi") {
            if state.history.count > 1 {
                Chart {
                    ForEach(Array(state.history.enumerated()), id: \.offset) { i, point in
                        LineMark(x: .value("Nokta", i), y: .value("Equity", point.equity))
                            .foregroundStyle(state.equity >= initialEquity ? .green : .orange)
                    }
                    RuleMark(y: .value("Başlangıç", initialEquity))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                        .foregroundStyle(.secondary)
                }
                .chartXAxis(.hidden)
                .chartYScale(domain: .automatic(includesZero: false))
                .frame(height: 180)
                .padding(.vertical, 4)
            } else {
                Text("Her döngüde bir nokta eklenir — eğri zamanla oluşacak.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func positionsSection(_ state: BotState) -> some View {
        Section("Açık pozisyonlar") {
            if state.positions.isEmpty {
                Text("Pozisyon yok — bot sinyal bekliyor")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(state.positions.sorted(by: { $0.key < $1.key }), id: \.key) { symbol, pos in
                    let pnl = pos.unrealizedPnl(current: state.prices[symbol])
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(symbol).font(.headline)
                            Text(pos.side == 1 ? "LONG" : "SHORT")
                                .font(.caption.bold())
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(pos.side == 1 ? .green.opacity(0.15) : .red.opacity(0.15))
                                .clipShape(Capsule())
                            Spacer()
                            Text(pnl, format: .currency(code: "USD"))
                                .foregroundStyle(pnl >= 0 ? .green : .red)
                        }
                        Text("Giriş \(pos.entryPrice, specifier: "%.2f") · Stop \(pos.stopPrice, specifier: "%.2f") · \(shortDate(pos.entryTime))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func tradesSection(_ state: BotState) -> some View {
        Section("Son işlemler") {
            if state.trades.isEmpty {
                Text("Henüz kapanan işlem yok").foregroundStyle(.secondary)
            } else {
                ForEach(state.trades.suffix(15).reversed()) { trade in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(trade.symbol) \(trade.side == 1 ? "long" : "short")")
                                .font(.subheadline)
                            Text("\(shortDate(trade.exitTime)) · \(trade.reason)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(trade.pnl, format: .currency(code: "USD"))
                            .foregroundStyle(trade.pnl >= 0 ? .green : .red)
                    }
                }
            }
        }
    }

    private var settingsSheet: some View {
        NavigationStack {
            Form {
                Section("Veri kaynağı (state.json adresi)") {
                    TextField("URL", text: loader.$urlString, axis: .vertical)
                        .font(.footnote.monospaced())
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }
                Section {
                    Button("Varsayılana dön") {
                        loader.urlString = StateLoader.defaultURL
                    }
                }
            }
            .navigationTitle("Ayarlar")
            .toolbar {
                Button("Tamam") {
                    showSettings = false
                    Task { await loader.load() }
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
