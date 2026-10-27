import CoreGraphics
import Foundation
import Testing
@testable import SumiCore

/// These run the real Python code from the repository venv, so the Swift side and
/// `sumi/service.py` cannot drift apart silently.
@Suite(.enabled(if: hasEngine), .serialized)
struct EngineIntegrationTests {
    @Test func `swift reads a frame written by the python preview buffer`() throws {
        let file = URL.temporaryDirectory.appending(path: "sumi-preview-\(UUID().uuidString).bin")
        defer { try? FileManager.default.removeItem(at: file) }
        // A 4×2 BGR frame: left half pure red, right half pure blue. Python mirrors it.
        let script = """
        import json, sys, numpy as np
        from sumi.service import PreviewBuffer
        frame = np.zeros((2, 4, 3), np.uint8)
        frame[:, :2] = (0, 0, 255)
        frame[:, 2:] = (255, 0, 0)
        buffer = PreviewBuffer(__import__('pathlib').Path(sys.argv[1]), 16, 16)
        print(json.dumps({'slot': buffer.write(frame, 5)[0], 'layout': buffer.describe()}))
        """
        let output = try run(["-B", "-c", script, file.path])
        let decoded = try JSONDecoder.snake.decode(Written.self, from: output)
        let reader = try PreviewReader(layout: decoded.layout)
        let image = try #require(reader.image(slot: decoded.slot))
        #expect(image.width == 4 && image.height == 2)
        let pixels = try #require(image.dataProvider?.data as Data?)
        // Mirrored: blue now on the left. BGRA bytes.
        #expect(Array(pixels[0..<4]) == [255, 0, 0, 255])
        #expect(Array(pixels[12..<16]) == [0, 0, 255, 255])
        #expect(reader.image(slot: 1 - decoded.slot) == nil, "unwritten slot must be rejected")
    }

    @Test func `latest picks the newest complete frame and nothing twice`() throws {
        let file = URL.temporaryDirectory.appending(path: "sumi-preview-\(UUID().uuidString).bin")
        defer { try? FileManager.default.removeItem(at: file) }
        let script = """
        import json, sys, numpy as np, pathlib
        from sumi.service import PreviewBuffer
        buffer = PreviewBuffer(pathlib.Path(sys.argv[1]), 8, 8)
        for number in (1, 2, 3):
            buffer.write(np.full((4, 4, 3), number, np.uint8), number)
        print(json.dumps({'slot': 0, 'layout': buffer.describe()}))
        """
        let decoded = try JSONDecoder.snake.decode(Written.self, from: run(["-B", "-c", script, file.path]))
        let reader = try PreviewReader(layout: decoded.layout)
        let newest = try #require(reader.latest(after: .min))
        #expect(newest.revision == 3)
        #expect(reader.latest(after: 3) == nil, "no new frame: the display link does nothing")
        #expect(reader.latest(after: 2)?.revision == 3)
    }

    @Test(.timeLimit(.minutes(1)))
    func `client launches the engine, changes a setting and shuts down`() async throws {
        let client = EngineClient(location: .repository(repository),
                                  logURL: URL.temporaryDirectory.appending(path: "sumi-test-engine.log"))
        client.launch()
        try await waitUntil { client.connection == .connected && client.state != nil }
        #expect(client.resources?.standardizedFileURL == repository.standardizedFileURL)

        // Resolution changes stay in memory; effects would rewrite the user's preferences.
        let target = try #require(EngineState.resolutions.first { $0 != client.state?.resolution })
        try await client.send(.setResolution(target))
        try await waitUntil { client.state?.resolution == target }

        await #expect(throws: EngineFailure(message: "Opção inválida.")) {
            try await client.send(.setResolution("1 × 1"))
        }
        await client.shutdown()
        try await waitUntil { client.connection == .idle }
        #expect(!client.isRunning)
    }

    private struct Written: Decodable {
        var slot: Int
        var layout: PreviewLayout
    }

    private func run(_ arguments: [String]) throws -> Data {
        let process = Process()
        process.executableURL = venvPython
        process.arguments = arguments
        process.currentDirectoryURL = repository
        let pipe = Pipe()
        process.standardOutput = pipe
        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        try #require(process.terminationStatus == 0)
        return data
    }

    private func waitUntil(_ condition: () -> Bool) async throws {
        for _ in 0..<300 where !condition() {
            try await Task.sleep(for: .milliseconds(100))
        }
        try #require(condition())
    }
}

extension JSONDecoder {
    static var snake: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
