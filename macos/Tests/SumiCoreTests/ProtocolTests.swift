import Foundation
import Testing
@testable import SumiCore

/// Repository root (…/macos/Tests/SumiCoreTests/ProtocolTests.swift → four levels up).
nonisolated let repository = URL(filePath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
nonisolated let venvPython = repository.appending(path: ".venv/bin/python")
nonisolated let hasEngine = FileManager.default.isExecutableFile(atPath: venvPython.path)

let stateLine = #"""
{"event":"state","state":{"running":false,"phase":"stopped","phase_label":"Câmera desligada","hidden":false,"step":"Sua câmera só liga quando você clicar em Iniciar.","hint":"","status":"Nenhuma imagem está sendo capturada.","progress":0.0,"fps":0.0,"performance":"Sem áudio","primary_label":"Iniciar câmera","primary_enabled":false,"recalibrate_enabled":false,"start_label":"Iniciar câmera","start_enabled":false,"inputs_enabled":true,"refresh_enabled":true,"cameras":["FaceTime HD"],"camera":"FaceTime HD","effect":"Portal","effects":["Portal","Instantâneo"],"resolution":"1280 × 720","hold":"1.0","output":"OBS Virtual Camera","outputs":["Só prévia","OBS Virtual Camera"],"dynamic_background":false,"background_description":"Usa a captura vazia inteira.","guide_title":"Abrir o portal","guide_instruction":"Mostre as duas palmas.","guide_image":"portal.png","guide_steps":["Um","Dois"],"output_help":"No Meet, escolha OBS Virtual Camera.","virtual_active":false,"meet_available":false,"meet_connected":false,"meet_status":"Integração Meet desligada.","main_notice":"","leave_enabled":false,"leave_delay":"2","leave_countdown":null,"preview_revision":-1}}
"""#

@Suite struct EventDecoding {
    @Test func `state carries every field the interface draws`() throws {
        let event = try #require(EngineEvent.decode(Array(stateLine.utf8)))
        guard case .state(let state) = event else { Issue.record("not a state: \(event)"); return }
        #expect(state.phaseLabel == "Câmera desligada")
        #expect(state.cameras == ["FaceTime HD"])
        #expect(state.leaveCountdown == nil)
        #expect(state.guideSteps.count == 2)
        #expect(!state.isLive)
    }

    @Test func `hello exposes resources and preview layout`() throws {
        let line = #"{"event":"hello","protocol":1,"version":"0.4.0","resources":"/tmp/repo","preview":{"path":"/tmp/p.bin","slots":2,"max_width":1280,"max_height":720,"format":"bgra","header_bytes":64,"slot_header_bytes":64,"slot_bytes":3686464}}"#
        let event = try #require(EngineEvent.decode(Array(line.utf8)))
        guard case .hello(let version, _, let resources, let preview) = event else {
            Issue.record("not hello"); return
        }
        #expect(version == 1)
        #expect(resources.path == "/tmp/repo")
        #expect(preview?.slotBytes == 64 + 1280 * 720 * 4)
    }

    @Test func `replies map to success or failure`() throws {
        #expect(EngineEvent.decode(Array(#"{"event":"reply","id":3,"ok":true,"value":"abc"}"#.utf8))
                == .reply(id: 3, result: .success("abc")))
        #expect(EngineEvent.decode(Array(#"{"event":"reply","id":4,"ok":false,"error":"Não"}"#.utf8))
                == .reply(id: 4, result: .failure(EngineFailure(message: "Não"))))
    }

    @Test(arguments: [
        "not json", "{}", #"{"event":"mystery"}"#, #"{"event":"reply","ok":true}"#,
        #"{"event":"open_url","url":"file:///etc/passwd"}"#,
    ])
    func `bad or unsafe lines are ignored`(line: String) {
        #expect(EngineEvent.decode(Array(line.utf8)) == nil)
    }

    @Test func `only https links are opened`() {
        #expect(EngineEvent.decode(Array(#"{"event":"open_url","url":"https://obsproject.com/download"}"#.utf8))
                == .openURL(URL(string: "https://obsproject.com/download")!))
    }
}

@Suite struct CommandEncoding {
    private func object(_ command: EngineCommand) throws -> [String: AnyHashable] {
        try #require(JSONSerialization.jsonObject(with: command.line(id: 9)) as? [String: AnyHashable])
    }

    @Test func `value commands send cmd and value`() throws {
        #expect(try object(.setEffect("Portal")) == ["id": 9, "cmd": "set_effect", "value": "Portal"])
    }

    @Test func `engine actions and toggles use the service field names`() throws {
        #expect(try object(.engine(.restore)) == ["id": 9, "cmd": "engine", "name": "restore"])
        #expect(try object(.setBackground(dynamic: true)) == ["id": 9, "cmd": "set_background", "dynamic": true])
        #expect(try object(.setLeave(enabled: false)) == ["id": 9, "cmd": "set_leave", "enabled": false])
    }

    @Test func `a line never contains a newline`() {
        let line = EngineCommand.setCamera("Câmera\nfalsa").line(id: 1)
        #expect(!line.contains(0x0A))
    }
}

@Suite struct EngineLocationTests {
    @Test func `repository layout runs main.py as a service`() {
        let location = EngineLocation.repository(URL(filePath: "/repo", directoryHint: .isDirectory))
        #expect(location.executable.path == "/repo/.venv/bin/python")
        #expect(location.arguments == ["-B", "main.py", "--service"])
    }

    @Test(.enabled(if: hasEngine))
    func `environment variable points to the repository`() {
        let location = EngineLocation.resolve(environment: ["SUMI_REPOSITORY": repository.path])
        #expect(location?.directory.standardizedFileURL == repository.standardizedFileURL)
    }

    @Test func `bundled engine wins over the repository`() throws {
        let manager = FileManager.default
        let app = manager.temporaryDirectory.appending(path: "Sumi-test-\(UUID().uuidString).app")
        defer { try? manager.removeItem(at: app) }
        let engine = app.appending(path: "Contents/Resources/engine/SumiEngine")
        try manager.createDirectory(at: engine.deletingLastPathComponent(), withIntermediateDirectories: true)
        #expect(manager.createFile(atPath: engine.path, contents: Data("#!/bin/sh\n".utf8),
                                   attributes: [.posixPermissions: 0o755]))
        let bundle = try #require(Bundle(url: app))
        let location = EngineLocation.resolve(bundle: bundle, environment: ["SUMI_REPOSITORY": repository.path])
        #expect(location?.executable.path == engine.path)
        #expect(location?.arguments == ["--service"])
        #expect(location?.directory.path == engine.deletingLastPathComponent().path)
    }

    @Test func `missing engine resolves to nil`() {
        #expect(EngineLocation.resolve(environment: ["SUMI_REPOSITORY": "/nonexistent"]) == nil)
    }
}
