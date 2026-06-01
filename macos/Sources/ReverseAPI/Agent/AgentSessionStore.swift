import Foundation
import Observation

@MainActor
@Observable
final class AgentSessionStore {
    private(set) var sessions: [AgentSessionSummary] = []
    private let rootDirectory: URL

    init(rootDirectory: URL) {
        self.rootDirectory = rootDirectory
        try? FileManager.default.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
        Task { await reload() }
    }

    func reload() async {
        let root = rootDirectory
        let summaries: [AgentSessionSummary] = await Task.detached(priority: .utility) {
            Self.scan(root: root)
        }.value
        sessions = summaries.sorted { $0.lastModifiedAt > $1.lastModifiedAt }
    }

    func save(_ record: AgentSessionRecord) async {
        let root = rootDirectory
        await Task.detached(priority: .utility) {
            Self.write(record: record, into: root)
        }.value
        await reload()
    }

    func load(id: String) async -> AgentSessionRecord? {
        let root = rootDirectory
        return await Task.detached(priority: .userInitiated) {
            Self.read(id: id, from: root)
        }.value
    }

    func delete(id: String) async {
        let root = rootDirectory
        await Task.detached(priority: .userInitiated) {
            let dir = root.appendingPathComponent(id, isDirectory: true)
            try? FileManager.default.removeItem(at: dir)
        }.value
        await reload()
    }

    // MARK: - File I/O

    nonisolated private static func write(record: AgentSessionRecord, into root: URL) {
        let dir = root.appendingPathComponent(record.id, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        let metadataURL = dir.appendingPathComponent("metadata.json")
        let metadata = AgentSessionMetadata(from: record)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(metadata) {
            try? data.write(to: metadataURL, options: .atomic)
        }

        let messagesURL = dir.appendingPathComponent("messages.jsonl")
        let jsonl = MessagesJSONL.encode(events: record.events)
        try? jsonl.write(to: messagesURL, options: .atomic)
    }

    nonisolated private static func read(id: String, from root: URL) -> AgentSessionRecord? {
        let dir = root.appendingPathComponent(id, isDirectory: true)
        let metadataURL = dir.appendingPathComponent("metadata.json")
        let messagesURL = dir.appendingPathComponent("messages.jsonl")
        guard let metadataData = try? Data(contentsOf: metadataURL) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let metadata = try? decoder.decode(AgentSessionMetadata.self, from: metadataData) else { return nil }
        let events: [AgentEvent]
        if let messagesData = try? Data(contentsOf: messagesURL) {
            events = MessagesJSONL.decode(data: messagesData)
        } else {
            events = []
        }
        return makeRecord(from: metadata, events: events)
    }

    // MARK: - Scan

    nonisolated private static func scan(root: URL) -> [AgentSessionSummary] {
        let fm = FileManager.default
        guard let entries = try? fm.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return [] }

        var summaries: [AgentSessionSummary] = []
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        for entry in entries {
            var isDir: ObjCBool = false
            guard fm.fileExists(atPath: entry.path, isDirectory: &isDir), isDir.boolValue else { continue }
            let metadataURL = entry.appendingPathComponent("metadata.json")
            guard let data = try? Data(contentsOf: metadataURL),
                  let metadata = try? decoder.decode(AgentSessionMetadata.self, from: data)
            else { continue }
            let count = countUserAssistantEvents(at: entry.appendingPathComponent("messages.jsonl"))
            summaries.append(AgentSessionSummary(
                id: metadata.id,
                title: metadata.title,
                createdAt: metadata.createdAt,
                lastModifiedAt: metadata.lastModifiedAt,
                messageCount: count
            ))
        }
        return summaries
    }

    nonisolated private static func countUserAssistantEvents(at url: URL) -> Int {
        guard let data = try? Data(contentsOf: url),
              let text = String(data: data, encoding: .utf8) else { return 0 }
        var count = 0
        text.enumerateLines { line, _ in
            if line.contains("\"type\":\"user\"") || line.contains("\"type\":\"assistant_text\"") {
                count += 1
            }
        }
        return count
    }

    // MARK: - Helpers

    nonisolated private static func makeRecord(from m: AgentSessionMetadata, events: [AgentEvent]) -> AgentSessionRecord {
        let history: [AgentHistoryItem] = events.compactMap { event in
            switch event {
            case .userText(_, let text): return AgentHistoryItem(role: "user", content: text)
            case .assistantText(_, _, let text): return AgentHistoryItem(role: "assistant", content: text)
            default: return nil
            }
        }
        return AgentSessionRecord(
            id: m.id,
            title: m.title,
            createdAt: m.createdAt,
            lastModifiedAt: m.lastModifiedAt,
            target: m.target,
            events: events,
            history: history,
            lastWorkdir: m.lastWorkdir,
            generatedFiles: m.generatedFiles,
            claudeSessionID: m.claudeSessionID,
            selectedModel: m.selectedModel,
            sessionUsage: m.sessionUsage
        )
    }
}

// MARK: - JSONL encode / decode

enum MessagesJSONL {
    static func encode(events: [AgentEvent]) -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        var out = Data()
        for event in events {
            guard let envelope = envelope(for: event) else { continue }
            guard let line = try? encoder.encode(envelope) else { continue }
            out.append(line)
            out.append(0x0A)
        }
        return out
    }

    static func decode(data: Data) -> [AgentEvent] {
        guard let text = String(data: data, encoding: .utf8) else { return [] }
        var events: [AgentEvent] = []
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        text.enumerateLines { line, _ in
            guard !line.isEmpty,
                  let lineData = line.data(using: .utf8),
                  let envelope = try? decoder.decode(Envelope.self, from: lineData),
                  let event = envelope.toEvent()
            else { return }
            events.append(event)
        }
        return events
    }

    private struct Envelope: Codable {
        let timestamp: Date
        let type: String
        let content: AnyCodableJSON?

        init(type: String, content: AnyCodableJSON?) {
            self.timestamp = Date()
            self.type = type
            self.content = content
        }

        func toEvent() -> AgentEvent? {
            switch type {
            case "user":
                guard let text = content?.string else { return nil }
                return .userText(eventID: UUID(), text: text)
            case "assistant_text":
                guard let text = content?.string else { return nil }
                return .assistantText(chatID: "", eventID: UUID(), text: text)
            case "tool_use":
                guard let obj = content?.object,
                      let name = obj["name"]?.string,
                      let input = obj["input"]?.toJSONString() else { return nil }
                return .toolUse(chatID: "", eventID: UUID(), name: name, inputJSON: input)
            case "tool_result":
                guard let obj = content?.object else { return nil }
                let output = obj["output"]?.string ?? ""
                let isError = obj["is_error"]?.bool ?? false
                return .toolResult(chatID: "", eventID: UUID(), output: output, isError: isError)
            case "file_written":
                guard let path = content?.string else { return nil }
                return .fileWritten(chatID: "", eventID: UUID(), path: path)
            case "complete":
                guard let obj = content?.object else { return nil }
                let workdir = obj["workdir"]?.string ?? ""
                let files = obj["files"]?.array?.compactMap { $0.string } ?? []
                return .complete(chatID: "", eventID: UUID(), workdir: workdir, files: files)
            case "error":
                let message = content?.string ?? "unknown error"
                return .error(chatID: nil, eventID: UUID(), message: message)
            case "session_started":
                guard let sid = content?.string else { return nil }
                return .sessionStarted(chatID: "", eventID: UUID(), claudeSessionID: sid)
            case "usage":
                guard let obj = content?.object else { return nil }
                let usage = AgentUsage(
                    model: obj["model"]?.string,
                    inputTokens: Int(obj["inputTokens"]?.double ?? 0),
                    outputTokens: Int(obj["outputTokens"]?.double ?? 0),
                    cacheCreationInputTokens: Int(obj["cacheCreationInputTokens"]?.double ?? 0),
                    cacheReadInputTokens: Int(obj["cacheReadInputTokens"]?.double ?? 0),
                    totalCostUsd: obj["totalCostUsd"]?.double,
                    durationMs: Int(obj["durationMs"]?.double ?? 0),
                    numTurns: Int(obj["numTurns"]?.double ?? 0)
                )
                return .usage(chatID: "", eventID: UUID(), usage: usage)
            default:
                return nil
            }
        }
    }

    private static func envelope(for event: AgentEvent) -> Envelope? {
        switch event {
        case .userText(_, let text):
            return Envelope(type: "user", content: .string(text))
        case .assistantText(_, _, let text):
            return Envelope(type: "assistant_text", content: .string(text))
        case .assistantTextChunk, .cancelled:
            return nil
        case .toolUse(_, _, let name, let inputJSON):
            let inputValue = AnyCodableJSON(jsonString: inputJSON) ?? .string(inputJSON)
            return Envelope(type: "tool_use", content: .object([
                "name": .string(name),
                "input": inputValue,
            ]))
        case .toolResult(_, _, let output, let isError):
            return Envelope(type: "tool_result", content: .object([
                "output": .string(output),
                "is_error": .bool(isError),
            ]))
        case .fileWritten(_, _, let path):
            return Envelope(type: "file_written", content: .string(path))
        case .complete(_, _, let workdir, let files):
            return Envelope(type: "complete", content: .object([
                "workdir": .string(workdir),
                "files": .array(files.map { .string($0) }),
            ]))
        case .error(_, _, let message):
            return Envelope(type: "error", content: .string(message))
        case .sessionStarted(_, _, let sid):
            return Envelope(type: "session_started", content: .string(sid))
        case .usage(_, _, let usage):
            var dict: [String: AnyCodableJSON] = [
                "inputTokens": .number(Double(usage.inputTokens)),
                "outputTokens": .number(Double(usage.outputTokens)),
                "cacheCreationInputTokens": .number(Double(usage.cacheCreationInputTokens)),
                "cacheReadInputTokens": .number(Double(usage.cacheReadInputTokens)),
                "durationMs": .number(Double(usage.durationMs)),
                "numTurns": .number(Double(usage.numTurns)),
            ]
            if let m = usage.model { dict["model"] = .string(m) }
            if let c = usage.totalCostUsd { dict["totalCostUsd"] = .number(c) }
            return Envelope(type: "usage", content: .object(dict))
        }
    }
}

// MARK: - Tiny JSON-value type for envelope content

enum AnyCodableJSON: Codable, Equatable {
    case string(String)
    case bool(Bool)
    case number(Double)
    case array([AnyCodableJSON])
    case object([String: AnyCodableJSON])
    case null

    init?(jsonString: String) {
        guard let data = jsonString.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        guard let v = try? decoder.decode(AnyCodableJSON.self, from: data) else { return nil }
        self = v
    }

    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    var string: String? { if case .string(let s) = self { return s } else { return nil } }
    var bool: Bool? { if case .bool(let b) = self { return b } else { return nil } }
    var double: Double? { if case .number(let n) = self { return n } else { return nil } }
    var array: [AnyCodableJSON]? { if case .array(let a) = self { return a } else { return nil } }
    var object: [String: AnyCodableJSON]? { if case .object(let o) = self { return o } else { return nil } }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let b = try? c.decode(Bool.self) { self = .bool(b); return }
        if let n = try? c.decode(Double.self) { self = .number(n); return }
        if let s = try? c.decode(String.self) { self = .string(s); return }
        if let a = try? c.decode([AnyCodableJSON].self) { self = .array(a); return }
        if let o = try? c.decode([String: AnyCodableJSON].self) { self = .object(o); return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "unsupported JSON shape")
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .bool(let b): try c.encode(b)
        case .number(let n): try c.encode(n)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        case .null: try c.encodeNil()
        }
    }
}
