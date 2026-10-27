import Foundation

/// One moment of the session, exactly as `ViewState.public()` sends it from Python.
public struct EngineState: Decodable, Equatable, Sendable {
    public var running: Bool
    public var phase: String
    public var phaseLabel: String
    public var hidden: Bool
    public var step: String
    public var hint: String
    public var status: String
    public var progress: Double
    public var fps: Double
    public var performance: String
    public var primaryLabel: String
    public var primaryEnabled: Bool
    public var recalibrateEnabled: Bool
    public var startLabel: String
    public var startEnabled: Bool
    public var inputsEnabled: Bool
    public var refreshEnabled: Bool
    public var cameras: [String]
    public var camera: String
    public var effect: String
    public var effects: [String]
    public var resolution: String
    public var hold: String
    public var output: String
    public var outputs: [String]
    public var dynamicBackground: Bool
    public var backgroundDescription: String
    public var guideTitle: String
    public var guideInstruction: String
    public var guideImage: String
    public var guideSteps: [String]
    public var outputHelp: String
    public var virtualActive: Bool
    public var meetAvailable: Bool
    public var meetConnected: Bool
    public var meetStatus: String
    public var mainNotice: String
    public var leaveEnabled: Bool
    public var leaveDelay: String
    public var leaveCountdown: Double?
    public var previewRevision: Int

    /// Values the engine accepts for the pickers. Kept here so the UI never offers others.
    public static let resolutions = ["1280 × 720", "640 × 480"]
    public static let holdTimes = ["0.8", "1.0", "1.5", "2.0"]
    public static let leaveDelays = ["2", "3", "5"]

    /// True while the camera session is between "Ao vivo" and "Desaparecido".
    public var isLive: Bool { running && phase != "opening" && phase != "error" }
}

/// Where the shared preview lives and how it is laid out (sent in `hello`).
public struct PreviewLayout: Decodable, Equatable, Sendable {
    public var path: String
    public var slots: Int
    public var maxWidth: Int
    public var maxHeight: Int
    public var format: String
    public var headerBytes: Int
    public var slotHeaderBytes: Int
    public var slotBytes: Int
}

/// Every line the engine writes to stdout.
public enum EngineEvent: Equatable, Sendable {
    case hello(protocolVersion: Int, version: String, resources: URL, preview: PreviewLayout?)
    case reply(id: Int, result: Result<String?, EngineFailure>)
    case state(EngineState)
    case preview(slot: Int, revision: Int)
    case openURL(URL)
    case error(String)
    case bye(stopped: Bool)

    private struct Envelope: Decodable {
        var event: String
        var `protocol`: Int?
        var version: String?
        var resources: String?
        var preview: PreviewLayout?
        var id: Int?
        var ok: Bool?
        var error: String?
        var value: String?
        var state: EngineState?
        var slot: Int?
        var revision: Int?
        var url: String?
        var message: String?
        var stopped: Bool?
    }

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    /// Decodes one protocol line. Unknown or malformed lines return nil and are ignored.
    public static func decode(_ line: some DataProtocol) -> EngineEvent? {
        guard let envelope = try? decoder.decode(Envelope.self, from: Data(line)) else { return nil }
        switch envelope.event {
        case "hello":
            guard let resources = envelope.resources else { return nil }
            return .hello(protocolVersion: envelope.protocol ?? 0, version: envelope.version ?? "?",
                          resources: URL(filePath: resources, directoryHint: .isDirectory),
                          preview: envelope.preview)
        case "reply":
            guard let id = envelope.id else { return nil }
            let result: Result<String?, EngineFailure> = envelope.ok == true
                ? .success(envelope.value)
                : .failure(EngineFailure(message: envelope.error ?? "Comando recusado."))
            return .reply(id: id, result: result)
        case "state":
            return envelope.state.map(EngineEvent.state)
        case "preview":
            guard let slot = envelope.slot, let revision = envelope.revision else { return nil }
            return .preview(slot: slot, revision: revision)
        case "open_url":
            guard let text = envelope.url, let url = URL(string: text),
                  url.scheme == "https" else { return nil }
            return .openURL(url)
        case "error":
            return .error(envelope.message ?? "Erro desconhecido no motor.")
        case "bye":
            return .bye(stopped: envelope.stopped ?? false)
        default:
            return nil
        }
    }
}

public struct EngineFailure: Error, Equatable, Sendable, LocalizedError {
    public var message: String
    public init(message: String) { self.message = message }
    public var errorDescription: String? { message }
}
