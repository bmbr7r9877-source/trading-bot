import Foundation
import SwiftUI

/// GitHub'a her push'tan sonra raw URL'den state.json'u ceker.
/// Bot 4 saatte bir karar verdigi icin raw CDN'in ~5 dk'lik cache'i sorun olmaz.
@MainActor
final class StateLoader: ObservableObject {
    @Published var state: BotState?
    @Published var errorMessage: String?
    @Published var loading = false

    @AppStorage("stateURL") var urlString = StateLoader.defaultURL

    static let defaultURL =
        "https://raw.githubusercontent.com/bmbr7r9877-source/trading-bot/main/paper/state.json"

    func load() async {
        guard let url = URL(string: urlString) else {
            errorMessage = "Geçersiz URL"
            return
        }
        loading = true
        defer { loading = false }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                errorMessage = "Sunucu \(http.statusCode) döndü — URL'i ayarlardan kontrol et"
                return
            }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            state = try decoder.decode(BotState.self, from: data)
            errorMessage = nil
        } catch {
            errorMessage = "Veri alınamadı: \(error.localizedDescription)"
        }
    }
}
