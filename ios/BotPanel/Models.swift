import Foundation

struct BotState: Decodable {
    var startedAt: String?
    var cash: Double
    var positions: [String: Position]
    var trades: [Trade]
    var history: [HistoryPoint]

    var equity: Double { history.last?.equity ?? cash }
    var prices: [String: Double] { history.last?.prices ?? [:] }
    var lastUpdate: String? { history.last?.ts }
}

struct Position: Decodable {
    var side: Int
    var qty: Double
    var entryPrice: Double
    var stopPrice: Double
    var entryTime: String
    var strategy: String

    func unrealizedPnl(current: Double?) -> Double {
        guard let current else { return 0 }
        return Double(side) * qty * (current - entryPrice)
    }
}

struct Trade: Decodable, Identifiable {
    var symbol: String
    var strategy: String
    var side: Int
    var qty: Double
    var entryTime: String
    var entryPrice: Double
    var exitTime: String
    var exitPrice: Double
    var pnl: Double
    var reason: String

    var id: String { exitTime + symbol + String(pnl) }
}

struct HistoryPoint: Decodable {
    var ts: String
    var equity: Double
    var prices: [String: Double]?
}

/// Python isoformat() ("2026-06-10T09:43:21.428983+00:00") -> "10.06 09:43"
func shortDate(_ iso: String?) -> String {
    guard let iso, iso.count >= 16 else { return "-" }
    let month = iso.dropFirst(5).prefix(2)
    let day = iso.dropFirst(8).prefix(2)
    let time = iso.dropFirst(11).prefix(5)
    return "\(day).\(month) \(time)"
}
