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
    dependencies: [
        // In-app updates: appcast + EdDSA-signed archives published with each GitHub release.
        .package(url: "https://github.com/sparkle-project/Sparkle", from: "2.6.0"),
    ],
    targets: [
        // Talks to the Python engine: process, JSON protocol and shared preview.
        .target(name: "SumiCore", swiftSettings: mainActorByDefault),
        // SwiftUI shell: windows, permissions, global shortcut, menu bar.
        .executableTarget(name: "Sumi",
                          dependencies: ["SumiCore", .product(name: "Sparkle", package: "Sparkle")],
                          swiftSettings: mainActorByDefault),
        .testTarget(name: "SumiCoreTests", dependencies: ["SumiCore"],
                    swiftSettings: mainActorByDefault),
    ]
)
