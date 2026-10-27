import Foundation
import Observation
import Sparkle

/// In-app updates through Sparkle: the appcast published with each GitHub release lists the newest
/// version, and the archive is accepted only when its EdDSA signature matches SUPublicEDKey.
///
/// Off in development builds (Info.plist has SumiRepository), which run the engine from the repository
/// and would otherwise be replaced by the released app.
@Observable
final class Updater {
    let enabled: Bool
    private(set) var canCheck = false
    @ObservationIgnored private let controller: SPUStandardUpdaterController
    @ObservationIgnored private var observation: NSKeyValueObservation?

    init(bundle: Bundle = .main) {
        enabled = bundle.object(forInfoDictionaryKey: "SumiRepository") == nil
            && bundle.object(forInfoDictionaryKey: "SUFeedURL") != nil
        controller = SPUStandardUpdaterController(startingUpdater: enabled, updaterDelegate: nil,
                                                  userDriverDelegate: nil)
        guard enabled else { return }
        observation = controller.updater.observe(\.canCheckForUpdates, options: [.initial, .new]) {
            [weak self] updater, _ in
            let value = updater.canCheckForUpdates
            Task { @MainActor in self?.canCheck = value }
        }
    }

    func check() { controller.checkForUpdates(nil) }

    /// Daily background check; Sparkle stores the choice in the app's defaults.
    var automaticallyChecks: Bool {
        get {
            access(keyPath: \.automaticallyChecks)
            return controller.updater.automaticallyChecksForUpdates
        }
        set {
            withMutation(keyPath: \.automaticallyChecks) {
                controller.updater.automaticallyChecksForUpdates = newValue
            }
        }
    }
}
