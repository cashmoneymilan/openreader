import Foundation

struct EngineHandshake: Decodable {
    let port: Int
    let pid: Int32
}

enum EngineState: Equatable {
    case starting
    case ready
    case stopped
    case failed(String)

    var label: String {
        switch self {
        case .starting: return "Starting engine"
        case .ready: return "Engine ready"
        case .stopped: return "Engine stopped"
        case .failed: return "Engine unavailable"
        }
    }
}

@MainActor
final class EngineSupervisor: ObservableObject {
    @Published private(set) var state: EngineState = .starting
    private(set) var port: Int?
    private(set) var token = UUID().uuidString
    private var process: Process?
    private var handshakeURL: URL?

    var baseURL: URL? {
        guard let port else { return nil }
        return URL(string: "http://127.0.0.1:\(port)")
    }

    func start() async {
        if process?.isRunning == true { return }
        state = .starting
        token = UUID().uuidString
        let handshake = FileManager.default.temporaryDirectory
            .appendingPathComponent("openreader-engine-\(ProcessInfo.processInfo.processIdentifier)-\(UUID().uuidString).json")
        handshakeURL = handshake

        guard let engineURL = locateEngine() else {
            state = .failed("Bundled engine not found. Build the app with scripts/package_macos.sh.")
            return
        }

        let process = Process()
        process.executableURL = engineURL
        process.arguments = [
            "serve", "--port", "0", "--token", token,
            "--handshake", handshake.path, "--log-level", "warning",
        ]
        let logPipe = Pipe()
        process.standardOutput = logPipe
        process.standardError = logPipe

        do {
            try process.run()
            self.process = process
        } catch {
            state = .failed("Could not launch the local engine: \(error.localizedDescription)")
            return
        }

        for _ in 0..<80 {
            if !process.isRunning {
                state = .failed("The local engine exited during startup.")
                return
            }
            if let data = try? Data(contentsOf: handshake),
               let decoded = try? JSONDecoder().decode(EngineHandshake.self, from: data) {
                port = decoded.port
                if await healthCheck() {
                    state = .ready
                    return
                }
            }
            try? await Task.sleep(for: .milliseconds(100))
        }
        state = .failed("The local engine did not become ready in time.")
    }

    func stop() {
        if process?.isRunning == true { process?.terminate() }
        process = nil
        port = nil
        if let handshakeURL { try? FileManager.default.removeItem(at: handshakeURL) }
        state = .stopped
    }

    func authorizedRequest(path: String) throws -> URLRequest {
        guard let baseURL, let url = URL(string: path, relativeTo: baseURL) else {
            throw URLError(.cannotConnectToHost)
        }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return request
    }

    private func healthCheck() async -> Bool {
        guard let baseURL, let url = URL(string: "/health", relativeTo: baseURL) else { return false }
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    private func locateEngine() -> URL? {
        if let bundled = Bundle.main.url(forResource: "openreader-engine", withExtension: nil) {
            return bundled
        }
        if let configured = ProcessInfo.processInfo.environment["OPENREADER_ENGINE_PATH"] {
            let url = URL(fileURLWithPath: configured)
            if FileManager.default.isExecutableFile(atPath: url.path) { return url }
        }
        let candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("dist/openreader-engine")
        return FileManager.default.isExecutableFile(atPath: candidate.path) ? candidate : nil
    }
}
