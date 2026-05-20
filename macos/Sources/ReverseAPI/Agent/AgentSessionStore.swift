import Foundation
import Observation

/// Owns the on-disk index of agent sessions: lists them, loads, saves,
/// deletes. Lives on the main actor since the UI binds directly to
/// `sessions`. Writes happen on a detached priority-utility task so the
/// main thread isn't blocked.
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
        // Most recently touched first
        sessions = summaries.sorted { $0.lastModifiedAt > $1.lastModifiedAt }
    }

    func save(_ record: AgentSessionRecord) async {
        let root = rootDirectory
        await Task.detached(priority: .utility) {
            let dir = root.appendingPathComponent(record.id, isDirectory: true)
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent("session.json")
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            encoder.dateEncodingStrategy = .iso8601
            guard let data = try? encoder.encode(record) else { return }
            try? data.write(to: url, options: .atomic)
        }.value
        await reload()
    }

    func load(id: String) async -> AgentSessionRecord? {
        let root = rootDirectory
        return await Task.detached(priority: .userInitiated) {
            let url = root
                .appendingPathComponent(id, isDirectory: true)
                .appendingPathComponent("session.json")
            guard let data = try? Data(contentsOf: url) else { return nil }
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            return try? decoder.decode(AgentSessionRecord.self, from: data)
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

    // MARK: - Internal scan

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
            let url = entry.appendingPathComponent("session.json")
            guard let data = try? Data(contentsOf: url),
                  let record = try? decoder.decode(AgentSessionRecord.self, from: data)
            else { continue }
            // Count only user/assistant turns for the message count badge —
            // tool plumbing makes the raw event count misleading.
            let messageCount = record.events.reduce(0) { acc, event in
                switch event {
                case .userText, .assistantText: return acc + 1
                default: return acc
                }
            }
            summaries.append(AgentSessionSummary(
                id: record.id,
                title: record.title,
                createdAt: record.createdAt,
                lastModifiedAt: record.lastModifiedAt,
                messageCount: messageCount
            ))
        }
        return summaries
    }
}
