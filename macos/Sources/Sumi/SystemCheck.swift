import AppKit
import AVFoundation
import Observation

/// What the Mac must provide: camera permission and the OBS virtual camera.
@Observable
final class SystemCheck {
    enum Camera { case unknown, allowed, denied }

    private(set) var camera: Camera = .unknown
    private(set) var obsInstalled = false
    private(set) var obsCameraReady = false

    static let cameraSettings = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")!
    static let extensionSettings = URL(string: "x-apple.systempreferences:com.apple.LoginItems-Settings.extension")!
    static let obsDownload = URL(string: "https://obsproject.com/download")!

    init() { refresh() }

    func refresh() {
        camera = switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: .allowed
        case .denied, .restricted: .denied
        default: .unknown
        }
        obsInstalled = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.obsproject.obs-studio") != nil
        let session = AVCaptureDevice.DiscoverySession(deviceTypes: [.external], mediaType: .video,
                                                       position: .unspecified)
        obsCameraReady = session.devices.contains { $0.localizedName.localizedCaseInsensitiveContains("OBS") }
    }

    /// Shows the system prompt with the text from Info.plist (only the first time).
    func requestCamera() async {
        if camera == .denied {
            NSWorkspace.shared.open(Self.cameraSettings)
            return
        }
        _ = await AVCaptureDevice.requestAccess(for: .video)
        refresh()
    }

    func openOBS() {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.obsproject.obs-studio") else {
            NSWorkspace.shared.open(Self.obsDownload)
            return
        }
        NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration())
    }
}
