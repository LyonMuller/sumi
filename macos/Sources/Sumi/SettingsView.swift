import SumiCore
import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            CameraSettings().tabItem { Label("Câmera", systemImage: "web.camera") }
            MeetSettings().tabItem { Label("Meet", systemImage: "video.bubble") }
            ShortcutSettings().tabItem { Label("Atalhos", systemImage: "keyboard") }
            UpdateSettings().tabItem { Label("Atualizações", systemImage: "arrow.down.circle") }
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
                Section {
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
                Section {
                    Picker("Contagem antes de capturar o fundo",
                           selection: engine.binding(\.captureTime, EngineCommand.setCaptureTime)) {
                        ForEach(EngineState.captureTimes, id: \.self) { Text("\($0) s").tag($0) }
                    }
                    Picker("Pausa depois do estalo", selection: engine.binding(\.snapDelay, EngineCommand.setSnapDelay)) {
                        ForEach(EngineState.snapDelays, id: \.self) {
                            Text($0 == "0" ? "Nenhuma" : "\($0) s").tag($0)
                        }
                    }
                } footer: {
                    Text("A pausa vale só para sumir com o estalo: dá tempo de falar antes do efeito.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
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
                    LabeledContent("Extensão") {
                        Text(state.meetConnected ? "Reunião vinculada" : state.meetExtension ? "Conectada" : "Não detectada")
                            .foregroundStyle(state.meetConnected ? .green : state.meetExtension ? .primary : .secondary)
                    }
                    Text(state.meetStatus).font(.caption).foregroundStyle(.secondary)
                } footer: {
                    Text("Sem código: com o Sumi aberto, a reunião aberta no Meet é vinculada sozinha.")
                }
                Section("Sons") {
                    Toggle("Sons dos efeitos", isOn: Binding(
                        get: { state.sounds }, set: { engine.perform(.setSounds(enabled: $0)) }))
                    Toggle("Tocar os sons na chamada", isOn: Binding(
                        get: { state.callSounds }, set: { engine.perform(.setCallSounds(enabled: $0)) }))
                        .disabled(!state.meetAvailable)
                    Text("Na chamada, os sons entram no seu microfone pelo Meet. Se você estiver mudo, ninguém ouve. Para usar seus próprios sons, ponha arquivos com o mesmo nome em ~/Library/Application Support/Sumi/sons.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section {
                    Toggle("Sair do Meet depois de desaparecer", isOn: Binding(
                        get: { state.leaveEnabled },
                        set: { engine.perform(.setLeave(enabled: $0)) }))
                        .disabled(!state.meetAvailable)
                    Picker("Esperar antes de sair", selection: engine.binding(\.leaveDelay, EngineCommand.setLeaveDelay)) {
                        ForEach(EngineState.leaveDelays, id: \.self) { Text("\($0) s").tag($0) }
                    }
                    .disabled(!state.meetAvailable)
                } footer: {
                    Text("A saída automática só fecha a aba da reunião vinculada. Restaurar cancela a contagem.")
                }
                Section("Instalar a extensão no Chrome") {
                    Button("Instalar no Chrome…") { install() }
                    Text("Abre a página de extensões do Chrome e mostra a pasta no Finder (o caminho fica copiado). Ative Modo do desenvolvedor, clique em Carregar sem compactação e escolha a pasta. Só é preciso fazer isso uma vez.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)
        } else {
            EngineNotReady()
        }
    }

    private func install() {
        Task {
            do {
                guard let path = try await engine.send(.extensionPath) else { return }
                let folder = URL(filePath: path)
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(path, forType: .string)
                NSWorkspace.shared.activateFileViewerSelecting([folder])
                let browsers = ["com.google.Chrome", "com.microsoft.edgemac", "com.brave.Browser", "company.thebrowser.Browser"]
                if let browser = browsers.lazy.compactMap({ NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) }).first,
                   let page = URL(string: browser.path.contains("Edge") ? "edge://extensions" : "chrome://extensions") {
                    try await NSWorkspace.shared.open([page], withApplicationAt: browser,
                                                      configuration: NSWorkspace.OpenConfiguration())
                }
                engine.show("Pasta da extensão copiada. No Chrome: Modo do desenvolvedor → Carregar sem compactação.")
            } catch { engine.show(error.localizedDescription) }
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

private struct UpdateSettings: View {
    @Environment(Updater.self) private var updater

    var body: some View {
        @Bindable var updater = updater
        Form {
            LabeledContent("Versão instalada") {
                Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—")
            }
            if updater.enabled {
                Toggle("Procurar atualizações automaticamente", isOn: $updater.automaticallyChecks)
                Button("Verificar agora") { updater.check() }
                    .disabled(!updater.canCheck)
            } else {
                Text("Build de desenvolvimento: atualize com git pull e macos/build-app.sh.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}
