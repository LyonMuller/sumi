import SumiCore
import SwiftUI

/// Quick controls during a call, without bringing the window forward.
struct MenuBarContent: View {
    @Environment(EngineClient.self) private var engine
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let state = engine.state
        Text(state?.phaseLabel ?? "Motor iniciando")
        if let state, state.primaryEnabled {
            Button(state.primaryLabel) { engine.perform(.primary) }
        }
        Button("Restaurar imagem (⌃⌥R)") { engine.perform(.engine(.restore)) }
            .disabled(state?.running != true)
        Divider()
        Button("Abrir janela") {
            openWindow(id: "main")
            NSApp.activate()
        }
        SettingsLink { Text("Ajustes…") }
        Divider()
        Button("Sair do Sumi") { NSApp.terminate(nil) }
            .keyboardShortcut("q")
    }
}
