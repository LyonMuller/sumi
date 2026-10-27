import SumiCore
import SwiftUI

struct RootView: View {
    @Environment(EngineClient.self) private var engine
    @Environment(SystemCheck.self) private var system
    @AppStorage("onboardingDone") private var onboardingDone = false

    private enum Route { case failure, onboarding, main }

    private var route: Route {
        if case .failed = engine.connection { return .failure }
        return !onboardingDone || system.camera != .allowed ? .onboarding : .main
    }

    var body: some View {
        ZStack {
            switch route {
            case .failure:
                if case .failed(let message) = engine.connection { EngineFailureView(message: message) }
            case .onboarding:
                OnboardingView { onboardingDone = true }
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            case .main:
                MainView()
                    .transition(.opacity.combined(with: .scale(scale: 1.02)))
            }
        }
        .animation(Motion.page, value: route)
        .frame(minWidth: 900, minHeight: 600)
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            system.refresh()
        }
    }
}

/// One place for timing, so the whole app moves the same way.
enum Motion {
    static let page = Animation.smooth(duration: 0.45)
    static let state = Animation.smooth(duration: 0.3)
    static let pop = Animation.spring(response: 0.35, dampingFraction: 0.78)
    /// The engine reports gesture progress at camera rate; this fills the gaps between reports.
    static let progress = Animation.linear(duration: 0.12)
}

struct MainView: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        HStack(spacing: 0) {
            StagePanel()
                .padding(20)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider()
            InspectorPanel()
                .frame(width: 320)
        }
        .toolbar {
            ToolbarItem(placement: .navigation) {
                PhaseBadge(state: engine.state)
            }
            ToolbarItemGroup(placement: .primaryAction) {
                CameraMenu()
                StartButton()
            }
        }
        .navigationTitle("Sumi")
    }
}

private struct StartButton: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        let running = engine.state?.running == true
        Button {
            engine.perform(running ? .stopCamera : .startCamera)
        } label: {
            Label(engine.state?.startLabel ?? "Iniciar câmera",
                  systemImage: running ? "stop.fill" : "video.fill")
                .contentTransition(.symbolEffect(.replace))
        }
        .labelStyle(.titleAndIcon)
        .disabled(engine.state?.startEnabled != true)
        .help("Liga ou desliga a webcam (⌘L)")
        .animation(Motion.state, value: running)
    }
}

// MARK: Stage

private struct StagePanel: View {
    @Environment(EngineClient.self) private var engine
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let state = engine.state
        let phase = state?.phase ?? "stopped"
        let tint = PhaseBadge.tint(for: phase)
        VStack(alignment: .leading, spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 16).fill(.black)
                PreviewPlaceholder(state: state, connecting: engine.connection != .connected)
                PreviewView(reader: engine.preview, active: state?.running == true)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                if state?.hidden == true && phase == "hidden" {
                    HiddenSeal()
                        .transition(.scale(scale: 0.85).combined(with: .opacity))
                }
            }
            .aspectRatio(16 / 9, contentMode: .fit)
            .overlay {
                // Edge light in the phase color: calm when live, brighter while acting.
                RoundedRectangle(cornerRadius: 16)
                    .strokeBorder(tint.opacity(Self.glow(for: phase)), lineWidth: 2)
                    .shadow(color: tint.opacity(Self.glow(for: phase) * 0.8), radius: 14)
            }
            .overlay(alignment: .top) { Banners(state: state, notice: engine.notice) }
            .overlay(alignment: .bottom) {
                if let state, state.progress > 0, phase == "holding" {
                    GestureProgress(progress: state.progress, hint: state.hint)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .frame(maxWidth: .infinity)
            .animation(reduceMotion ? nil : Motion.pop, value: phase)
            .animation(reduceMotion ? nil : Motion.pop, value: state?.progress ?? 0 > 0)

            if let state {
                Text(state.step)
                    .font(.title3.weight(.medium))
                    .fixedSize(horizontal: false, vertical: true)
                    .contentTransition(.opacity)
                    .animation(Motion.state, value: state.step)
                Actions(state: state)
                StatusLine(state: state)
            }
            Spacer(minLength: 0)
        }
    }

    static func glow(for phase: String) -> Double {
        switch phase {
        case "holding", "teleporting": 0.9
        case "hidden": 0.7
        case "ready": 0.35
        case "calibrating", "confirm", "uncalibrated", "error": 0.5
        default: 0
        }
    }
}

/// Shown over the frozen background while you are out of the picture.
private struct HiddenSeal: View {
    var body: some View {
        Label("Sumido", systemImage: "eye.slash.fill")
            .font(.title3.weight(.semibold))
            .symbolEffect(.pulse, options: .repeating)
            .padding(.horizontal, 18).padding(.vertical, 10)
            .background(.ultraThinMaterial, in: Capsule())
            .environment(\.colorScheme, .dark)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            .padding(16)
    }
}

private struct PreviewPlaceholder: View {
    let state: EngineState?
    let connecting: Bool

    var body: some View {
        VStack(spacing: 12) {
            if connecting {
                ProgressView().controlSize(.large).tint(.white)
                Text("Preparando o motor…")
            } else if state?.running == true {
                ProgressView().controlSize(.large).tint(.white)
                Text(state?.phaseLabel ?? "Abrindo câmera")
            } else {
                Image(systemName: "video.slash")
                    .font(.system(size: 44, weight: .light))
                    .symbolEffect(.bounce, value: state?.running)
                Text(state?.phaseLabel ?? "Câmera desligada").font(.title3)
            }
        }
        .foregroundStyle(.white.opacity(0.75))
        .animation(Motion.state, value: state?.running)
    }
}

private struct Banners: View {
    let state: EngineState?
    let notice: String?

    var body: some View {
        VStack(spacing: 8) {
            if let countdown = state?.leaveCountdown {
                banner("Saindo do Meet em \(Int(countdown.rounded(.up))) s. Restaurar cancela.",
                       systemImage: "door.left.hand.open", tint: .orange)
                    .contentTransition(.numericText(countsDown: true))
            }
            if let notice {
                banner(notice, systemImage: "exclamationmark.triangle.fill", tint: .yellow)
            }
            if let message = state?.mainNotice, !message.isEmpty {
                banner(message, systemImage: "info.circle.fill", tint: .blue)
            }
        }
        .padding(12)
        .animation(Motion.pop, value: notice)
        .animation(Motion.pop, value: state?.mainNotice)
        .animation(Motion.pop, value: state?.leaveCountdown.map { Int($0.rounded(.up)) })
    }

    private func banner(_ text: String, systemImage: String, tint: Color) -> some View {
        Label(text, systemImage: systemImage)
            .symbolRenderingMode(.multicolor)
            .font(.callout)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(.regularMaterial, in: Capsule())
            .overlay(Capsule().strokeBorder(tint.opacity(0.4)))
            .transition(.move(edge: .top).combined(with: .opacity))
    }
}

private struct GestureProgress: View {
    let progress: Double
    let hint: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !hint.isEmpty {
                Text(hint).font(.callout.weight(.medium)).contentTransition(.opacity)
            }
            ProgressView(value: min(max(progress, 0), 1))
                .progressViewStyle(.linear)
                .tint(.orange)
                .animation(Motion.progress, value: progress)
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .environment(\.colorScheme, .dark)
        .padding(14)
    }
}

private struct Actions: View {
    @Environment(EngineClient.self) private var engine
    let state: EngineState

    var body: some View {
        HStack(spacing: 10) {
            Button { engine.perform(.primary) } label: {
                Text(state.primaryLabel)
                    .contentTransition(.interpolate)
                    .frame(minWidth: 170)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.extraLarge)
            .disabled(!state.primaryEnabled)
            .keyboardShortcut(.return, modifiers: .command)
            .animation(Motion.state, value: state.primaryLabel)

            Button("Refazer fundo") { engine.perform(.engine(.calibrate)) }
                .controlSize(.extraLarge)
                .disabled(!state.recalibrateEnabled)

            Spacer()

            Button { engine.perform(.engine(.restore)) } label: {
                Label("Restaurar", systemImage: "arrow.uturn.backward")
            }
            .controlSize(.extraLarge)
            .disabled(!state.running)
            .help("Volta para a imagem ao vivo. Também funciona com F8 ou ⌃⌥R em qualquer app.")
        }
    }
}

private struct StatusLine: View {
    let state: EngineState

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(state.status).contentTransition(.opacity)
            Spacer()
            if state.running {
                Text("\(Int(state.fps.rounded())) FPS")
                    .monospacedDigit()
                    .contentTransition(.numericText(value: state.fps.rounded()))
            }
        }
        .font(.callout)
        .foregroundStyle(.secondary)
        .lineLimit(2)
        .animation(Motion.state, value: state.status)
        .animation(Motion.state, value: Int(state.fps.rounded()))
    }
}

struct PhaseBadge: View {
    let state: EngineState?

    var body: some View {
        let phase = state?.phase ?? "stopped"
        let tint = Self.tint(for: phase)
        HStack(spacing: 6) {
            Image(systemName: "circle.fill")
                .font(.system(size: 8))
                .foregroundStyle(tint)
                // Breathing dot while the camera is live, like a recording light.
                .symbolEffect(.pulse, options: .repeating, isActive: phase == "ready" || phase == "hidden")
            Text(state?.phaseLabel ?? "Conectando")
                .contentTransition(.interpolate)
        }
        .font(.callout.weight(.medium))
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(tint.opacity(0.14), in: Capsule())
        .animation(Motion.state, value: phase)
    }

    static func tint(for phase: String) -> Color {
        switch phase {
        case "ready": .green
        case "hidden": .purple
        case "holding", "teleporting": .orange
        case "error": .red
        case "uncalibrated", "calibrating", "confirm", "opening": .yellow
        default: .secondary
        }
    }
}

private struct CameraMenu: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        if let state = engine.state {
            Picker(selection: engine.binding(\.camera, EngineCommand.setCamera)) {
                if !state.cameras.contains(state.camera) { Text(state.camera).tag(state.camera) }
                ForEach(state.cameras, id: \.self) { Text($0).tag($0) }
            } label: {
                Label("Câmera", systemImage: "web.camera")
            }
            .pickerStyle(.menu)
            .disabled(!state.inputsEnabled)
            .help("Webcam usada pelo efeito")
        }
    }
}

// MARK: Inspector

private struct InspectorPanel: View {
    @Environment(EngineClient.self) private var engine

    var body: some View {
        if let state = engine.state {
            Form {
                Section("Efeito") {
                    Picker("Efeito", selection: engine.binding(\.effect, EngineCommand.setEffect)) {
                        ForEach(state.effects, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    GestureCard(state: state, resources: engine.resources)
                }
                Section {
                    Picker("Fundo", selection: Binding(
                        get: { state.dynamicBackground },
                        set: { engine.perform(.setBackground(dynamic: $0)) })) {
                        Text("Estático").tag(false)
                        Text("Em movimento").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .disabled(!state.inputsEnabled)
                    Text(state.backgroundDescription)
                        .font(.caption).foregroundStyle(.secondary)
                        .contentTransition(.opacity)
                        .animation(Motion.state, value: state.backgroundDescription)
                } header: {
                    Text("Fundo")
                }
                Section("Chamada") {
                    Picker("Saída", selection: engine.binding(\.output, EngineCommand.setOutput)) {
                        ForEach(state.outputs, id: \.self) { Text($0).tag($0) }
                    }
                    .disabled(!state.inputsEnabled)
                    LabeledContent("Câmera virtual") {
                        Label(state.virtualActive ? "Enviando" : "Parada",
                              systemImage: state.virtualActive ? "dot.radiowaves.left.and.right" : "pause.circle")
                            .foregroundStyle(state.virtualActive ? .green : .secondary)
                            .symbolEffect(.variableColor.iterative, options: .repeating, isActive: state.virtualActive)
                            .contentTransition(.symbolEffect(.replace))
                    }
                    Text(state.outputHelp).font(.caption).foregroundStyle(.secondary)
                    Button("Preparar vídeo para o Meet") { engine.perform(.prepareMeet) }
                        .disabled(!state.inputsEnabled)
                    if state.meetAvailable {
                        LabeledContent("Meet") {
                            Text(state.meetConnected ? "Vinculado" : "Não vinculado")
                                .foregroundStyle(state.meetConnected ? .green : .secondary)
                        }
                    }
                }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .animation(Motion.state, value: state.virtualActive)
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

private struct GestureCard: View {
    let state: EngineState
    let resources: URL?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Group {
                if let image = GuideImages.image(named: state.guideImage, in: resources) {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: 150)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
            }
            .id(state.guideImage)
            .transition(.opacity.combined(with: .scale(scale: 0.96)))
            VStack(alignment: .leading, spacing: 10) {
                Text(state.guideTitle).font(.headline)
                Text(state.guideInstruction).font(.callout).foregroundStyle(.secondary)
                ForEach(Array(state.guideSteps.enumerated()), id: \.offset) { index, step in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(index + 1)")
                            .font(.caption.weight(.bold)).monospacedDigit()
                            .frame(width: 18, height: 18)
                            .background(.tint.opacity(0.15), in: Circle())
                        Text(step).font(.callout)
                    }
                }
            }
            .id(state.guideTitle)
            .transition(.opacity)
        }
        .padding(.vertical, 4)
        .animation(Motion.state, value: state.guideImage)
    }
}

// MARK: Engine failure

private struct EngineFailureView: View {
    @Environment(EngineClient.self) private var engine
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label("O motor não está rodando", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message).textSelection(.enabled)
        } actions: {
            Button("Tentar de novo") { engine.restart() }
                .buttonStyle(.borderedProminent)
        }
    }
}

extension EngineClient {
    /// Two-way binding for a picker: reads the engine state, writes a command.
    func binding(_ key: KeyPath<EngineState, String>,
                 _ command: @escaping (String) -> EngineCommand) -> Binding<String> {
        Binding(get: { self.state?[keyPath: key] ?? "" },
                set: { self.perform(command($0)) })
    }
}
