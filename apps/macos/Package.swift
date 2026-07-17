// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OpenReaderMac",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "OpenReader", targets: ["OpenReaderMac"]),
    ],
    targets: [
        .executableTarget(name: "OpenReaderMac"),
    ],
    swiftLanguageModes: [.v5]
)
