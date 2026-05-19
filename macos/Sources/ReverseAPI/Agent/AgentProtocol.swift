import Foundation
import ReverseAPIProxy

enum AgentTargetLanguage: String, CaseIterable, Identifiable, Sendable {
    case python
    case typescript
    case go

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .python: return "Python"
        case .typescript: return "TypeScript"
        case .go: return "Go"
        }
    }
}

struct AgentFlowPayload: Encodable {
    static let defaultMaxBodyBytes = 64 * 1024

    let id: String
    let scheme: String
    let method: String
    let url: String
    let requestHeaders: [[String]]
    let requestBody: String?
    let responseStatus: Int?
    let responseHeaders: [[String]]
    let responseBody: String?
    let startedAt: Double
    let finishedAt: Double?

    init(_ flow: CapturedFlow, maxBodyBytes: Int = AgentFlowPayload.defaultMaxBodyBytes) {
        self.id = flow.id.uuidString
        self.scheme = flow.scheme.rawValue
        self.method = flow.method
        self.url = flow.url
        self.requestHeaders = flow.requestHeaders.map { [$0.name, $0.value] }
        self.requestBody = AgentFlowPayload.encodedBody(flow.requestBody, limit: maxBodyBytes)
        self.responseStatus = flow.responseStatus
        self.responseHeaders = flow.responseHeaders.map { [$0.name, $0.value] }
        self.responseBody = AgentFlowPayload.encodedBody(flow.responseBody, limit: maxBodyBytes)
        self.startedAt = flow.startedAt.timeIntervalSince1970
        self.finishedAt = flow.finishedAt?.timeIntervalSince1970
    }

    static func encodedBody(_ data: Data, limit: Int) -> String? {
        guard !data.isEmpty else { return nil }
        if data.count > limit {
            let head = data.prefix(limit)
            let suffix = "\n…<truncated \(data.count - limit) bytes>"
            if let text = String(data: head, encoding: .utf8) {
                return text + suffix
            }
            return "<binary:\(data.count) bytes, truncated>"
        }
        if let text = String(data: data, encoding: .utf8) { return text }
        return "<binary:\(data.count) bytes>"
    }
}

struct AgentHistoryItem: Encodable {
    let role: String
    let content: String
}

struct AgentChatRequest: Encodable {
    let type = "chat"
    let id: String
    let message: String
    let target: String
    let flows: [AgentFlowPayload]
    let history: [AgentHistoryItem]
}

enum AgentEvent: Sendable, Identifiable {
    case assistantText(chatID: String, eventID: UUID, text: String)
    case toolUse(chatID: String, eventID: UUID, name: String, inputJSON: String)
    case toolResult(chatID: String, eventID: UUID, output: String, isError: Bool)
    case fileWritten(chatID: String, eventID: UUID, path: String)
    case complete(chatID: String, eventID: UUID, workdir: String, files: [String])
    case error(chatID: String?, eventID: UUID, message: String)

    var id: UUID {
        switch self {
        case .assistantText(_, let id, _): return id
        case .toolUse(_, let id, _, _): return id
        case .toolResult(_, let id, _, _): return id
        case .fileWritten(_, let id, _): return id
        case .complete(_, let id, _, _): return id
        case .error(_, let id, _): return id
        }
    }
}

enum AgentEventDecoder {
    static func decode(_ data: Data) throws -> AgentEvent {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String else {
            throw DecodeError.invalidPayload
        }
        let chatID = object["id"] as? String
        let eventID = UUID()
        switch type {
        case "assistant_text":
            return .assistantText(
                chatID: chatID ?? "",
                eventID: eventID,
                text: object["text"] as? String ?? ""
            )
        case "tool_use":
            let name = object["name"] as? String ?? ""
            let inputObject = object["input"] as? [String: Any] ?? [:]
            let inputJSON = (try? JSONSerialization.data(withJSONObject: inputObject, options: [.prettyPrinted])).flatMap { String(data: $0, encoding: .utf8) } ?? ""
            return .toolUse(chatID: chatID ?? "", eventID: eventID, name: name, inputJSON: inputJSON)
        case "tool_result":
            return .toolResult(
                chatID: chatID ?? "",
                eventID: eventID,
                output: object["output"] as? String ?? "",
                isError: object["is_error"] as? Bool ?? false
            )
        case "file_written":
            return .fileWritten(
                chatID: chatID ?? "",
                eventID: eventID,
                path: object["path"] as? String ?? ""
            )
        case "complete":
            let files = (object["files"] as? [String]) ?? []
            return .complete(
                chatID: chatID ?? "",
                eventID: eventID,
                workdir: object["workdir"] as? String ?? "",
                files: files
            )
        case "error":
            return .error(
                chatID: chatID,
                eventID: eventID,
                message: object["message"] as? String ?? "unknown error"
            )
        default:
            throw DecodeError.unknownType(type)
        }
    }

    enum DecodeError: Error {
        case invalidPayload
        case unknownType(String)
    }
}
