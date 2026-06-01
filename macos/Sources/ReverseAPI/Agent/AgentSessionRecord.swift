import Foundation

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
    var claudeSessionID: String?
    var selectedModel: String?
    var sessionUsage: AgentUsage?
}

struct AgentSessionMetadata: Codable {
    var id: String
    var title: String
    var createdAt: Date
    var lastModifiedAt: Date
    var target: AgentTargetLanguage
    var lastWorkdir: String?
    var generatedFiles: [String]
    var claudeSessionID: String?
    var selectedModel: String?
    var sessionUsage: AgentUsage?

    init(from record: AgentSessionRecord) {
        self.id = record.id
        self.title = record.title
        self.createdAt = record.createdAt
        self.lastModifiedAt = record.lastModifiedAt
        self.target = record.target
        self.lastWorkdir = record.lastWorkdir
        self.generatedFiles = record.generatedFiles
        self.claudeSessionID = record.claudeSessionID
        self.selectedModel = record.selectedModel
        self.sessionUsage = record.sessionUsage
    }
}

struct AgentSessionSummary: Identifiable, Hashable, Sendable {
    let id: String
    let title: String
    let createdAt: Date
    let lastModifiedAt: Date
    let messageCount: Int
}
