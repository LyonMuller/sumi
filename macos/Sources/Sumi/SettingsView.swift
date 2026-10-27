import SumiCore
import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            CameraSettings().tabItem { Label("Câmera", systemImage: "web.camera") }
            MeetSettings().tabItem { Label("Meet", systemImage: "video.bubble") }
            ShortcutSettings().tabItem { Label("Atalhos", systemImage: "keyboard") }
        }
        .frame(width: 520)
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct CameraSettings: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        if let state = engine.state {
            Form {
                Picker("Webcam", selection: engine.binding(\.camera, EngineCommand.setCamera)) {
                    if !state.cameras.contains(state.camera) { Text(state.camera).tag(state.camera) }
                    ForEach(state.cameras, id: \.self) { Text($0).tag($0) }
                }
                Button("Atualizar lista") { engine.perform(.refreshCameras) }
                    .disabled(!state.refreshEnabled)
                Picker("Resolução", selection: engine.binding(\.resolution, EngineCommand.setResolution)) {
                    ForEach(EngineState.resolutions, id: \.self) { Text($0).tag($0) }
                }
                Picker("Tempo do gesto", selection: engine.binding(\.hold, EngineCommand.setHold)) {
                    ForEach(EngineState.holdTimes, id: \.self) { Text("\($0) s").tag($0) }
                }
                Picker("Saída", selection: engine.binding(\.output, EngineCommand.setOutput)) {
                    ForEach(state.outputs, id: \.self) { Text($0).tag($0) }
                }
                if !state.inputsEnabled {
                    Text("Pare a câmera para mudar estes ajustes.").font(.caption).foregroundStyle(.secondary)
                }
            }
            .disabled(!state.inputsEnabled)
            .formStyle(.grouped)
        } else {
            EngineNotReady()
        }
    }
}

private struct MeetSettings: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        if let state = engine.state {
            Form {
                Section {
                    LabeledContent("Situação", value: state.meetStatus)
                    Toggle("Sair do Meet depois de desaparecer", isOn: Binding(
                        get: { state.leaveEnabled },
                        set: { engine.perform(.setLeave(enabled: $0)) }))
                        .disabled(!state.meetAvailable)
                    Picker("Esperar antes de sair", selection: engine.binding(\.leaveDelay, EngineCommand.setLeaveDelay)) {
                        ForEach(EngineState.leaveDelays, id: \.self) { Text("\($0) s").tag($0) }
                    }
                    .disabled(!state.meetAvailable)
                } footer: {
                    Text("A saída automática só age na aba do Meet vinculada pela extensão. Restaurar cancela a contagem.")
                }
                Section("Extensão do Chrome") {
                    Button("Mostrar pasta da extensão") {
                        Task {
                            do {
                                if let path = try await engine.send(.extensionPath) {
                                    NSWorkspace.shared.activateFileViewerSelecting([URL(filePath: path)])
                                }
                            } catch { engine.show(error.localizedDescription) }
                        }
                    }
                    Button("Copiar código de vínculo") {
                        Task {
                            do {
                                if let code = try await engine.send(.pairingCode) {
                                    NSPasteboard.general.clearContents()
                                    NSPasteboard.general.setString(code, forType: .string)
                                    engine.show("Código copiado. Cole na extensão aberta na aba do Meet.")
                                }
                            } catch { engine.show(error.localizedDescription) }
                        }
                    }
                    .disabled(!state.meetAvailable)
                    Text("No Chrome: chrome://extensions → Modo do desenvolvedor → Carregar sem compactação → escolha a pasta.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)
        } else {
            EngineNotReady()
        }
    }
}

private struct ShortcutSettings: View {
    var body: some View {
        Form {
            LabeledContent("Restaurar em qualquer app") {
                VStack(alignment: .trailing) {
                    Text("F8").font(.body.monospaced())
                    Text("⌃⌥R").font(.body.monospaced())
                }
            }
            Text("Em teclados Apple, F8 controla a música. Use fn+F8, ou ⌃⌥R.")
                .font(.caption).foregroundStyle(.secondary)
            LabeledContent("Ação principal", value: "⌘↩")
            LabeledContent("Restaurar (com a janela ativa)", value: "⌘R")
            LabeledContent("Ligar ou parar a câmera", value: "⌘L")
            LabeledContent("Refazer fundo", value: "⇧⌘B")
        }
        .formStyle(.grouped)
    }
}

private struct EngineNotReady: View {
    var body: some View {
        Text("O motor ainda está iniciando.").foregroundStyle(.secondary).padding(40)
    }
}
