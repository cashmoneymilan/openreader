import AppKit
import Combine
import Foundation

enum WorkPhase: Equatable {
    case waiting
    case converting
    case ready
    case probing
    case sending
    case sent
    case failed(String)
}

enum DeviceKind: String, CaseIterable, Identifiable {
    case crosspoint
    case stock

    var id: String { rawValue }
    var label: String { self == .crosspoint ? "CrossPoint" : "Stock Xteink" }
    var defaultURL: String { self == .crosspoint ? "http://crosspoint.local" : "http://192.168.3.3" }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var selectedPDF: URL?
    @Published var phase: WorkPhase = .waiting
    @Published var conversion: ConversionReport?
    @Published var transfer: TransferReport?
    @Published var requestFilePicker = false
    @Published var deviceKind: DeviceKind = .crosspoint
    @Published var deviceURL = DeviceKind.crosspoint.defaultURL
    @Published var deviceFolder = "/Books"
    @Published var probeMessage = "Start File Transfer on the reader before connecting."
    let engine = EngineSupervisor()
    private var reportID: String?
    private var cancellables = Set<AnyCancellable>()

    init() {
        engine.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
        Task { await engine.start() }
    }

    func choose(_ url: URL) {
        guard url.pathExtension.caseInsensitiveCompare("pdf") == .orderedSame else {
            phase = .failed("Choose a PDF for the Milestone 0 conversion proof.")
            return
        }
        selectedPDF = url
        conversion = nil
        transfer = nil
        reportID = nil
        phase = .waiting
    }

    func updateDeviceKind(_ kind: DeviceKind) {
        deviceKind = kind
        deviceURL = kind.defaultURL
        probeMessage = "Start File Transfer on the reader before connecting."
        transfer = nil
    }

    func convert() async {
        guard let selectedPDF else { return }
        guard engine.state == .ready else {
            phase = .failed("The local conversion engine is not ready.")
            return
        }
        phase = .converting
        conversion = nil
        transfer = nil
        do {
            var request = try engine.authorizedRequest(path: "/v1/convert")
            request.httpMethod = "POST"
            let boundary = "OpenReader-\(UUID().uuidString)"
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            var body = Data()
            body.appendUTF8("--\(boundary)\r\n")
            body.appendUTF8("Content-Disposition: form-data; name=\"file\"; filename=\"\(selectedPDF.lastPathComponent)\"\r\n")
            body.appendUTF8("Content-Type: application/pdf\r\n\r\n")
            body.append(try Data(contentsOf: selectedPDF))
            body.appendUTF8("\r\n--\(boundary)--\r\n")
            request.httpBody = body
            let data = try await perform(request)
            let envelope = try JSONDecoder.openReader.decode(ConversionEnvelope.self, from: data)
            reportID = envelope.reportId
            conversion = envelope.report
            phase = .ready
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    func probe() async {
        phase = .probing
        do {
            var request = try engine.authorizedRequest(path: "/v1/devices/probe")
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: [
                "adapter": deviceKind.rawValue,
                "base_url": deviceURL,
            ])
            let data = try await perform(request)
            let report = try JSONDecoder.openReader.decode(DeviceProbeReport.self, from: data)
            probeMessage = report.reachable ? "\(deviceKind.label) is reachable for this sync session." : "The reader did not answer."
            phase = conversion == nil ? .waiting : .ready
        } catch {
            probeMessage = error.localizedDescription
            phase = conversion == nil ? .waiting : .ready
        }
    }

    func send() async {
        guard let reportID, conversion != nil else { return }
        phase = .sending
        transfer = nil
        do {
            var request = try engine.authorizedRequest(path: "/v1/devices/send")
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: [
                "adapter": deviceKind.rawValue,
                "base_url": deviceURL,
                "report_id": reportID,
                "folder": deviceFolder,
                "verify_readback": deviceKind == .crosspoint,
            ])
            let data = try await perform(request)
            transfer = try JSONDecoder.openReader.decode(TransferReport.self, from: data)
            phase = .sent
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    func openPreview() {
        guard let path = conversion?.preview else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func revealEPUB() {
        guard let path = conversion?.output else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let detail = (try? JSONDecoder().decode(APIErrorPayload.self, from: data).detail) ?? "The local engine returned an unexpected response."
            throw NSError(domain: "OpenReader", code: (response as? HTTPURLResponse)?.statusCode ?? -1, userInfo: [NSLocalizedDescriptionKey: detail])
        }
        return data
    }
}
