// swift-tools-version: 6.2
import PackageDescription

let mainActorByDefault: [SwiftSetting] = [.defaultIsolation(MainActor.self)]

let package = Package(
    name: "Sumi",
    defaultLocalization: "pt-BR",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "Sumi", targets: ["Sumi"]),
    ],
    targets: [
        // Talks to the Python engine: process, JSON protocol and shared preview.
        .target(name: "SumiCore", swiftSettings: mainActorByDefault),
        // SwiftUI shell: windows, permissions, global shortcut, menu bar.
        .executableTarget(name: "Sumi", dependencies: ["SumiCore"],
                          swiftSettings: mainActorByDefault),
        .testTarget(name: "SumiCoreTests", dependencies: ["SumiCore"],
                    swiftSettings: mainActorByDefault),
    ]
)
