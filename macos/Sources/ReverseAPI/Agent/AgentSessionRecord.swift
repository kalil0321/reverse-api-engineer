import Foundation

/// Persistent on-disk representation of one agent conversation. Saved as
/// `<agent-sessions-root>/<id>/session.json` next to the `flows/` +
/// `out/` directories the Python sidecar already writes into for the
/// same chat id, so everything for a given conversation lives in one
/// folder.
struct AgentSessionRecord: Codable {
    var id: String
    var title: String
    var createdAt: Date
    var lastModifiedAt: Date
    var target: AgentTargetLanguage
    var events: [AgentEvent]
    var history: [AgentHistoryItem]
    var lastWorkdir: String?
    var generatedFiles: [String]
    /// Claude Agent SDK session id captured on the first turn. When set,
    /// subsequent sends pass it as `resume` so the SDK rehydrates the
    /// conversation context on its end — we don't need to ship our
    /// `history` array back over the wire.
    var claudeSessionID: String?
}

/// Lightweight summary shown in the sessions list — avoids decoding the
/// full event timeline when we're just rendering a row.
struct AgentSessionSummary: Identifiable, Hashable, Sendable {
    let id: String
    let title: String
    let createdAt: Date
    let lastModifiedAt: Date
    let messageCount: Int
}
