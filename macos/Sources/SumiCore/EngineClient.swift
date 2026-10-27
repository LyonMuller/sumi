import CoreGraphics
import Foundation
import Observation
import os

/// How to start the Python engine.
public struct EngineLocation: Equatable, Sendable {
    public var executable: URL
    public var arguments: [String]
    public var directory: URL

    /// Development: the repository's venv runs `main.py --service`.
    public static func repository(_ root: URL) -> EngineLocation {
        EngineLocation(executable: root.appending(path: ".venv/bin/python"),
                       arguments: ["-B", "main.py", "--service"], directory: root)
    }

    /// Bundled engine first (finished `.app`), then `SUMI_REPOSITORY`, then the
    /// repository path `build-app.sh --dev` wrote into Info.plist.
    public static func resolve(bundle: Bundle = .main,
                               environment: [String: String] = ProcessInfo.processInfo.environment,
                               fileManager: FileManager = .default) -> EngineLocation? {
        // Resources, not Helpers: codesign requires every file under Helpers to be signed code, while
        // Resources are sealed as data (the PyInstaller folder mixes both; its Mach-O files are signed one by one).
        let helper = bundle.bundleURL.appending(path: "Contents/Resources/engine/SumiEngine")
        if fileManager.isExecutableFile(atPath: helper.path) {
            return EngineLocation(executable: helper, arguments: ["--service"],
                                  directory: helper.deletingLastPathComponent())
        }
        let candidates = [environment["SUMI_REPOSITORY"],
                          bundle.object(forInfoDictionaryKey: "SumiRepository") as? String]
        for case let path? in candidates where !path.isEmpty {
            let location = repository(URL(filePath: path, directoryHint: .isDirectory))
            if fileManager.isExecutableFile(atPath: location.executable.path) { return location }
        }
        return nil
    }
}

@Observable
public final class EngineClient {
    public enum Connection: Equatable {
        case idle, launching, connected, stopping, failed(String)
    }

    public private(set) var connection: Connection = .idle
    public private(set) var state: EngineState?
    /// Shared preview; a display-linked view reads frames from it directly.
    public private(set) var preview: PreviewReader?
    /// Folder with `assets/` (gesture illustrations).
    public private(set) var resources: URL?
    /// Last refusal or engine error, shown briefly by the interface.
    public private(set) var notice: String?
    /// Called for `open_url` events (OBS download page, for example).
    @ObservationIgnored public var openURL: (URL) -> Void = { _ in }

    @ObservationIgnored private let location: EngineLocation?
    @ObservationIgnored private let logURL: URL
    @ObservationIgnored private var process: Process?
    @ObservationIgnored private var input: FileHandle?
    @ObservationIgnored private var reader: Task<Void, Never>?
    @ObservationIgnored private let previewURL = URL.temporaryDirectory
        .appending(path: "Sumi-preview-\(getpid()).bin")
    @ObservationIgnored private var nextID = 1
    @ObservationIgnored private var pending: [Int: CheckedContinuation<String?, Error>] = [:]
    @ObservationIgnored private var activity: (any NSObjectProtocol)?
    @ObservationIgnored private var noticeTask: Task<Void, Never>?
    @ObservationIgnored private let log = Logger(subsystem: "dev.lyon.Sumi", category: "engine")

    public init(location: EngineLocation? = EngineLocation.resolve(),
                logURL: URL = URL.libraryDirectory.appending(path: "Logs/Sumi/engine.log")) {
        self.location = location
        self.logURL = logURL
        // A write to a dead engine must fail with an error, not kill the app.
        signal(SIGPIPE, SIG_IGN)
    }

    public var isRunning: Bool { process?.isRunning == true }

    // MARK: Lifecycle

    public func launch() {
        guard process == nil else { return }
        guard let location else {
            connection = .failed("Não encontrei o motor do Sumi. Baixe o app de novo; em desenvolvimento, rode macos/build-app.sh --dev.")
            return
        }
        let process = Process()
        process.executableURL = location.executable
        process.arguments = location.arguments + ["--preview", previewURL.path]
        process.currentDirectoryURL = location.directory
        let stdin = Pipe(), stdout = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = openLog()
        process.terminationHandler = { [weak self] finished in
            let status = finished.terminationStatus
            Task { @MainActor in self?.ended(status: status) }
        }
        connection = .launching
        do {
            try process.run()
        } catch {
            connection = .failed("O motor não abriu: \(error.localizedDescription)")
            return
        }
        log.info("Engine started, pid \(process.processIdentifier, privacy: .public)")
        self.process = process
        self.input = stdin.fileHandleForWriting
        let lines = stdout.fileHandleForReading.bytes.lines
        reader = Task { [weak self] in
            do {
                for try await line in lines {
                    guard let event = EngineEvent.decode(Array(line.utf8)) else { continue }
                    self?.receive(event)
                }
            } catch {
                self?.log.error("Engine output failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// Asks the engine to release camera and output, then waits for it to exit.
    public func shutdown(timeout: Duration = .seconds(7)) async {
        guard let process, process.isRunning else { return }
        connection = .stopping
        try? write(.shutdown, id: takeID())
        try? input?.close()
        let deadline = ContinuousClock.now + timeout
        while process.isRunning, ContinuousClock.now < deadline {
            try? await Task.sleep(for: .milliseconds(100))
        }
        if process.isRunning {
            log.error("Engine did not stop in time; terminating")
            process.terminate()
        }
    }

    public func restart() {
        guard process == nil else { return }
        connection = .idle
        launch()
    }

    // MARK: Commands

    /// Sends a command and waits for its reply. Throws `EngineFailure` when refused.
    @discardableResult
    public func send(_ command: EngineCommand) async throws -> String? {
        guard isRunning else { throw EngineFailure(message: "O motor não está rodando.") }
        let id = takeID()
        return try await withCheckedThrowingContinuation { continuation in
            pending[id] = continuation
            do {
                try write(command, id: id)
            } catch {
                pending[id] = nil
                continuation.resume(throwing: EngineFailure(message: "O motor parou de responder."))
            }
        }
    }

    /// Fire-and-forget for buttons: refusals show up as `notice`.
    public func perform(_ command: EngineCommand) {
        Task {
            do { try await send(command) } catch { show(error.localizedDescription) }
        }
    }

    public func show(_ message: String) {
        notice = message
        noticeTask?.cancel()
        noticeTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(6))
            guard !Task.isCancelled else { return }
            self?.notice = nil
        }
    }

    // MARK: Private

    private func takeID() -> Int {
        defer { nextID += 1 }
        return nextID
    }

    private func write(_ command: EngineCommand, id: Int) throws {
        guard let input else { throw EngineFailure(message: "O motor não está rodando.") }
        try input.write(contentsOf: command.line(id: id) + Data([0x0A]))
    }

    private func receive(_ event: EngineEvent) {
        switch event {
        case .hello(let protocolVersion, let version, let resources, let layout):
            log.info("Engine \(version, privacy: .public), protocol \(protocolVersion)")
            guard protocolVersion == 1 else {
                connection = .failed("Versão do motor incompatível com o app (protocolo \(protocolVersion)).")
                return
            }
            self.resources = resources
            if let layout {
                do { preview = try PreviewReader(layout: layout) } catch {
                    log.error("Preview unavailable: \(String(describing: error), privacy: .public)")
                }
            }
            connection = .connected
        case .reply(let id, let result):
            pending.removeValue(forKey: id)?.resume(with: result.mapError { $0 as Error })
        case .state(let state):
            if state.running != self.state?.running { keepAwake(state.running) }
            self.state = state
        case .preview:
            break // The preview view polls the shared buffer on every screen refresh.
        case .openURL(let url):
            openURL(url)
        case .error(let message):
            show(message)
        case .bye(let stopped):
            log.info("Engine said bye, camera released: \(stopped)")
        }
    }

    private func ended(status: Int32) {
        let expected = connection == .stopping
        log.info("Engine exited with status \(status)")
        reader?.cancel()
        reader = nil
        process = nil
        input = nil
        preview = nil
        try? FileManager.default.removeItem(at: previewURL)
        keepAwake(false)
        for continuation in pending.values {
            continuation.resume(throwing: EngineFailure(message: "O motor fechou."))
        }
        pending.removeAll()
        state = nil
        connection = expected ? .idle : .failed("O motor fechou inesperadamente (código \(status)). Veja \(logURL.path).")
    }

    /// Keeps App Nap from throttling video while the camera is on.
    private func keepAwake(_ running: Bool) {
        if running, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(
                options: [.userInitiated, .latencyCritical, .idleDisplaySleepDisabled],
                reason: "Câmera do Sumi ligada")
        } else if !running, let current = activity {
            ProcessInfo.processInfo.endActivity(current)
            activity = nil
        }
    }

    private func openLog() -> FileHandle? {
        let manager = FileManager.default
        try? manager.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !manager.fileExists(atPath: logURL.path) {
            manager.createFile(atPath: logURL.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: logURL) else { return nil }
        _ = try? handle.seekToEnd()
        return handle
    }
}
