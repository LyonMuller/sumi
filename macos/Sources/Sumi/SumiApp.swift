import AppKit
import SumiCore
import SwiftUI

@main
struct SumiApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @AppStorage("onboardingDone") private var onboardingDone = false

    var body: some Scene {
        Window("Sumi", id: "main") {
            RootView()
                .environment(delegate.engine)
                .environment(delegate.system)
        }
        .defaultSize(width: 1120, height: 720)
        .windowToolbarStyle(.unified)
        .commands {
            SessionCommands(engine: delegate.engine)
            CommandGroup(after: .help) {
                Button("Mostrar boas-vindas…") { onboardingDone = false }
            }
        }

        Settings {
            SettingsView()
                .environment(delegate.engine)
                .environment(delegate.system)
        }

        MenuBarExtra {
            MenuBarContent()
                .environment(delegate.engine)
        } label: {
            Image(systemName: delegate.engine.state?.hidden == true ? "theatermasks.fill" : "theatermasks")
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let engine = EngineClient()
    let system = SystemCheck()
    private var hotKeys: HotKeys?

    func applicationDidFinishLaunching(_ notification: Notification) {
        engine.openURL = { NSWorkspace.shared.open($0) }
        engine.launch()
        // F8 (fn+F8 on Apple keyboards) and ⌃⌥R restore the live image from any app.
        hotKeys = HotKeys { [engine] in engine.perform(.engine(.restore)) }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard engine.isRunning else { return .terminateNow }
        // Release camera and virtual output before quitting.
        Task {
            await engine.shutdown()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

struct SessionCommands: Commands {
    let engine: EngineClient

    var body: some Commands {
        CommandMenu("Câmera") {
            Button(engine.state?.primaryLabel ?? "Ação principal") { engine.perform(.primary) }
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(engine.state?.primaryEnabled != true)
            Button("Restaurar imagem ao vivo") { engine.perform(.engine(.restore)) }
                .keyboardShortcut("r", modifiers: .command)
                .disabled(engine.state?.running != true)
            Button("Refazer fundo") { engine.perform(.engine(.calibrate)) }
                .keyboardShortcut("b", modifiers: [.command, .shift])
                .disabled(engine.state?.recalibrateEnabled != true)
            Divider()
            Button(engine.state?.running == true ? "Parar câmera" : "Iniciar câmera") {
                engine.perform(engine.state?.running == true ? .stopCamera : .startCamera)
            }
            .keyboardShortcut("l", modifiers: .command)
            .disabled(engine.state?.startEnabled != true)
        }
    }
}
