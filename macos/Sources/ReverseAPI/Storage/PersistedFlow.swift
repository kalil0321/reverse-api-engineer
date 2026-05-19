import Foundation
import GRDB
import ReverseAPIProxy

struct PersistedFlow: Codable, FetchableRecord, PersistableRecord, Identifiable {
    static let databaseTableName = "flow"

    var id: String
    var scheme: String
    var method: String
    var host: String
    var port: Int
    var path: String
    var requestHeadersJSON: Data
    var requestBody: Data
    var responseStatus: Int?
    var responseHeadersJSON: Data?
    var responseBody: Data
    var startedAt: Double
    var finishedAt: Double?
    var errorMessage: String?

    enum Columns {
        static let id = Column("id")
        static let startedAt = Column("startedAt")
    }
}

enum FlowConversionError: Error {
    case invalidUUID
    case invalidScheme
}

extension PersistedFlow {
    init(from flow: CapturedFlow) throws {
        let encoder = JSONEncoder()
        let requestPairs = flow.requestHeaders.map { [$0.name, $0.value] }
        let responsePairs = flow.responseHeaders.map { [$0.name, $0.value] }
        self.init(
            id: flow.id.uuidString,
            scheme: flow.scheme.rawValue,
            method: flow.method,
            host: flow.host,
            port: flow.port,
            path: flow.path,
            requestHeadersJSON: try encoder.encode(requestPairs),
            requestBody: flow.requestBody,
            responseStatus: flow.responseStatus,
            responseHeadersJSON: flow.responseHeaders.isEmpty ? nil : try encoder.encode(responsePairs),
            responseBody: flow.responseBody,
            startedAt: flow.startedAt.timeIntervalSince1970,
            finishedAt: flow.finishedAt?.timeIntervalSince1970,
            errorMessage: flow.error
        )
    }

    func toCapturedFlow() throws -> CapturedFlow {
        guard let uuid = UUID(uuidString: id) else { throw FlowConversionError.invalidUUID }
        guard let parsedScheme = CapturedFlow.Scheme(rawValue: scheme) else { throw FlowConversionError.invalidScheme }
        let decoder = JSONDecoder()
        let requestPairs = (try? decoder.decode([[String]].self, from: requestHeadersJSON)) ?? []
        let responsePairs: [[String]]
        if let data = responseHeadersJSON,
           let decoded = try? decoder.decode([[String]].self, from: data) {
            responsePairs = decoded
        } else {
            responsePairs = []
        }
        var flow = CapturedFlow(
            id: uuid,
            scheme: parsedScheme,
            method: method,
            host: host,
            port: port,
            path: path,
            requestHeaders: requestPairs.compactMap { pair in
                guard pair.count == 2 else { return nil }
                return HTTPHeader(pair[0], pair[1])
            },
            startedAt: Date(timeIntervalSince1970: startedAt)
        )
        flow.requestBody = requestBody
        flow.responseStatus = responseStatus
        flow.responseHeaders = responsePairs.compactMap { pair in
            guard pair.count == 2 else { return nil }
            return HTTPHeader(pair[0], pair[1])
        }
        flow.responseBody = responseBody
        flow.finishedAt = finishedAt.map { Date(timeIntervalSince1970: $0) }
        flow.error = errorMessage
        return flow
    }
}
