import Foundation

struct ConversionEnvelope: Decodable {
    let reportId: String
    let report: ConversionReport
}

struct ConversionReport: Decodable {
    let source: String
    let immutableOriginal: String
    let output: String
    let preview: String
    let structureManifest: String
    let pages: Int
    let mode: String
    let supportTier: String
    let tierReasons: [String]
    let normalizedTextRetention: Double?
    let validation: ValidationReport
}

struct ValidationReport: Decodable {
    let valid: Bool
    let packageVersion: String?
    let chapters: Int
    let images: Int
    let issues: [ValidationIssue]
}

struct ValidationIssue: Decodable, Identifiable {
    var id: String { "\(code)-\(message)" }
    let level: String
    let code: String
    let message: String
}

struct TransferReport: Decodable {
    let adapter: String
    let destination: String
    let evidence: String
    let expectedSha256: String
    let observedSha256: String?
    let expectedSize: Int
    let observedSize: Int?
    let observations: [String]
}

struct DeviceProbeReport: Decodable {
    let adapter: String
    let reachable: Bool
}

struct APIErrorPayload: Decodable {
    let detail: String
}

extension JSONDecoder {
    static var openReader: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}

extension Data {
    mutating func appendUTF8(_ value: String) {
        append(value.data(using: .utf8)!)
    }
}
