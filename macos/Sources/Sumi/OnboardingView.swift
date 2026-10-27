import SumiCore
import SwiftUI

/// First run: camera permission (required), OBS virtual camera (for calls), Meet (optional).
struct OnboardingView: View {
    @Environment(SystemCheck.self) private var system
    @Environment(EngineClient.self) private var engine
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    let finish: () -> Void

    /// Fades and lifts each block in after the previous one.
    private func entrance(_ order: Int) -> some ViewModifier {
        Entrance(visible: appeared || reduceMotion, delay: Double(order) * 0.07)
    }

    var body: some View {
        VStack(spacing: 28) {
            VStack(spacing: 8) {
                Image(nsImage: NSApp.applicationIconImage)
                    .resizable()
                    .frame(width: 96, height: 96)
                    .scaleEffect(appeared || reduceMotion ? 1 : 0.8)
                    .animation(Motion.pop.delay(0.05), value: appeared)
                Text("Boas-vindas ao Sumi").font(.largeTitle.weight(.semibold))
                Text("Três passos para sumir da chamada com um gesto.")
                    .font(.title3).foregroundStyle(.secondary)
            }
            .modifier(entrance(0))

            VStack(spacing: 14) {
                StepRow(number: 1, title: "Permitir a câmera",
                        detail: cameraDetail, done: system.camera == .allowed) {
                    if system.camera != .allowed {
                        Button(system.camera == .denied ? "Abrir Ajustes" : "Permitir câmera") {
                            Task { await system.requestCamera() }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .modifier(entrance(1))
                StepRow(number: 2, title: "Instalar e ativar a câmera virtual do OBS",
                        detail: obsDetail, done: system.obsCameraReady) {
                    if !system.obsInstalled {
                        Button("Baixar OBS") { NSWorkspace.shared.open(SystemCheck.obsDownload) }
                    } else if !system.obsCameraReady {
                        HStack {
                            Button("Abrir OBS") { system.openOBS() }
                            Button("Extensões…") { NSWorkspace.shared.open(SystemCheck.extensionSettings) }
                        }
                    }
                }
                .modifier(entrance(2))
                StepRow(number: 3, title: "Ligar a câmera e capturar o fundo",
                        detail: "Depois de começar, clique em Iniciar câmera, saia do enquadramento e confirme o fundo vazio.",
                        done: false) { EmptyView() }
                    .modifier(entrance(3))
            }
            .frame(maxWidth: 640)
            .animation(Motion.pop, value: system.camera)
            .animation(Motion.pop, value: system.obsCameraReady)

            HStack {
                Button("Verificar de novo") { system.refresh() }
                Spacer()
                Button("Começar") { finish() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .disabled(system.camera != .allowed || engine.connection != .connected)
            }
            .frame(maxWidth: 640)
            .modifier(entrance(4))
            if !system.obsCameraReady && system.camera == .allowed {
                Text("Sem o OBS, o efeito funciona só na prévia. Você pode instalar depois.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear { appeared = true }
    }

    private var cameraDetail: String {
        switch system.camera {
        case .allowed: "Câmera liberada. O Sumi só liga a webcam quando você clicar em Iniciar."
        case .denied: "O acesso foi negado. Em Ajustes do Sistema → Privacidade → Câmera, ative o Sumi."
        case .unknown: "O macOS vai perguntar uma vez. Nada é gravado nem enviado para a internet."
        }
    }

    private var obsDetail: String {
        if system.obsCameraReady { return "OBS Virtual Camera encontrada. No Meet, escolha essa câmera." }
        if system.obsInstalled {
            return "Abra o OBS, clique em Iniciar Câmera Virtual uma vez e aprove a extensão em Ajustes → Geral → Itens de Início e Extensões. Depois pode fechar o OBS."
        }
        return "O OBS é gratuito e cria a câmera que o Meet, o Teams e o Zoom enxergam."
    }
}

private struct StepRow<Accessory: View>: View {
    let number: Int
    let title: String
    let detail: String
    let done: Bool
    @ViewBuilder let accessory: () -> Accessory

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                Circle().fill(done ? Color.green : Color.accentColor.opacity(0.15))
                if done {
                    Image(systemName: "checkmark").font(.headline).foregroundStyle(.white)
                        .transition(.scale(scale: 0.4).combined(with: .opacity))
                } else {
                    Text("\(number)").font(.headline).foregroundStyle(.tint)
                        .transition(.opacity)
                }
            }
            .frame(width: 30, height: 30)
            .scaleEffect(done ? 1 : 0.94)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline)
                Text(detail).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            accessory()
        }
        .padding(16)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(.green.opacity(done ? 0.35 : 0)))
    }
}

private struct Entrance: ViewModifier {
    let visible: Bool
    let delay: Double

    func body(content: Content) -> some View {
        content
            .opacity(visible ? 1 : 0)
            .offset(y: visible ? 0 : 12)
            .animation(.smooth(duration: 0.5).delay(delay), value: visible)
    }
}
