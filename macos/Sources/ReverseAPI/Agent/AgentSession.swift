import Foundation
import Observation
import ReverseAPIProxy

@MainActor
@Observable
final class AgentSession {
    enum Status: Equatable {
        case idle
        case launching
        case ready
        case streaming
        case failed
    }

    /// What the agent panel renders: the list of past sessions, or the
    /// timeline of the active session.
    enum Mode: Equatable {
        case list
        case session
    }

    private(set) var status: Status = .idle
    private(set) var events: [AgentEvent] = []
    private(set) var lastError: String?
    private(set) var lastWorkdir: String?
    private(set) var generatedFiles: [String] = []
    private(set) var history: [AgentHistoryItem] = []

    var input: String = ""
    var target: AgentTargetLanguage = .python
    var mode: Mode = .list

    var selectedModel: String = "claude-sonnet-4-6"
    private(set) var sessionUsage: AgentUsage = .zero

    let store: AgentSessionStore

    private let sidecar = AgentSidecar()
    private let client = AgentClient()
    private var receiverTask: Task<Void, Never>?
    private(set) var sessionID = UUID().uuidString
    private var sessionCreatedAt = Date()
    private var sessionTitle: String?
    /// Passed back as `resume` so the SDK rehydrates the conversation
    /// without us replaying `history`.
    private var claudeSessionID: String?
    private let workdir: URL
    private let launchSpec: AgentSidecar.LaunchSpec

    init(workdir: URL, launchSpec: AgentSidecar.LaunchSpec? = nil) {
        self.workdir = workdir
        self.launchSpec = launchSpec ?? .python3(workdir: workdir)
        self.store = AgentSessionStore(rootDirectory: workdir)
    }

    // MARK: - Session lifecycle

    func startNewSession() {
        events.removeAll()
        history.removeAll()
        generatedFiles = []
        lastWorkdir = nil
        lastError = nil
        sessionID = UUID().uuidString
        sessionCreatedAt = Date()
        sessionTitle = nil
        claudeSessionID = nil
        sessionUsage = .zero
        if status == .failed { status = .idle }
        mode = .session
    }

    func openSession(id: String) async {
        guard let record = await store.load(id: id) else { return }
        events = record.events
        history = record.history
        generatedFiles = record.generatedFiles
        lastWorkdir = record.lastWorkdir
        target = record.target
        sessionID = record.id
        sessionCreatedAt = record.createdAt
        sessionTitle = record.title
        claudeSessionID = record.claudeSessionID
        if let savedModel = record.selectedModel { selectedModel = savedModel }
        sessionUsage = record.sessionUsage ?? .zero
        lastError = nil
        if status == .failed { status = .idle }
        mode = .session
    }

    func backToList() {
        mode = .list
    }

    func deleteSession(id: String) async {
        if sessionID == id {
            startNewSession()
            mode = .list
        }
        await store.delete(id: id)
    }

    func ensureRunning() async {
        switch status {
        case .ready, .streaming, .launching:
            return
        case .idle, .failed:
            break
        }
        status = .launching
        do {
            let endpoint = try await sidecar.launch(launchSpec)
            try await client.connect(port: endpoint.port, token: endpoint.token)
            startReceiver()
            status = .ready
            lastError = nil
        } catch {
            await sidecar.terminate()
            await client.disconnect()
            lastError = "Agent sidecar failed to start: \(error)"
            status = .failed
        }
    }

    func send(flows: [CapturedFlow]) async {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        await ensureRunning()
        guard status == .ready || status == .streaming else { return }
        let userHistoryItem = AgentHistoryItem(role: "user", content: trimmed)
        let historyToSend: [AgentHistoryItem] = claudeSessionID == nil ? history : []
        let request = AgentChatRequest(
            id: sessionID,
            message: trimmed,
            target: target.rawValue,
            flows: flows.map { AgentFlowPayload($0) },
            history: historyToSend,
            claudeSessionId: claudeSessionID,
            model: selectedModel.isEmpty ? nil : selectedModel
        )
        history.append(userHistoryItem)
        events.append(.userText(eventID: UUID(), text: trimmed))
        if sessionTitle == nil {
            sessionTitle = Self.deriveTitle(from: trimmed)
        }
        await persist()
        do {
            input = ""
            status = .streaming
            try await client.send(request)
        } catch {
            lastError = "Failed to send chat: \(error)"
            status = .failed
        }
    }

    func cancel() async {
        guard status == .streaming else { return }
        let request = AgentCancelRequest(id: sessionID)
        do {
            try await client.cancel(request)
        } catch {
            // Local fallback so the UI doesn't stay stuck on the stop
            // button if the cancel send itself fails.
            lastError = "Failed to send cancel: \(error)"
            status = .ready
        }
    }

    func clear() {
        events.removeAll()
        history.removeAll()
        generatedFiles = []
        lastWorkdir = nil
        lastError = nil
        sessionID = UUID().uuidString
        sessionCreatedAt = Date()
        sessionTitle = nil
        claudeSessionID = nil
        sessionUsage = .zero
        if status == .failed { status = .idle }
    }

    func shutdown() async {
        receiverTask?.cancel()
        receiverTask = nil
        await client.disconnect()
        await sidecar.terminate()
        status = .idle
    }

    private func startReceiver() {
        receiverTask?.cancel()
        receiverTask = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let stream = await self.client.events()
                for try await event in stream {
                    self.handle(event)
                }
            } catch {
                await self.client.disconnect()
                await self.sidecar.terminate()
                self.lastError = "Agent stream error: \(error)"
                self.status = .failed
            }
        }
    }

    private func handle(_ event: AgentEvent) {
        switch event {
        case .assistantTextChunk(let chatID, _, let chunk):
            if let lastIndex = events.indices.last,
               case .assistantText(let c, let id, let existing) = events[lastIndex],
               c == chatID {
                events[lastIndex] = .assistantText(chatID: c, eventID: id, text: existing + chunk)
            } else {
                events.append(.assistantText(chatID: chatID, eventID: UUID(), text: chunk))
            }
        case .assistantText(_, _, let text):
            events.append(event)
            history.append(.init(role: "assistant", content: text))
        case .complete(_, _, let workdir, let files):
            events.append(event)
            lastWorkdir = workdir
            generatedFiles = files
            status = .ready
            recordStreamedAssistantTextIntoHistory()
        case .error(_, _, let message):
            events.append(event)
            lastError = message
            status = .failed
        case .sessionStarted(_, _, let claudeID):
            if !claudeID.isEmpty { claudeSessionID = claudeID }
        case .usage(_, _, let turnUsage):
            sessionUsage = sessionUsage + turnUsage
        case .cancelled:
            status = .ready
            recordStreamedAssistantTextIntoHistory()
            // Drop the SDK session id after a cancel — Claude CLI may
            // have written a partial/aborted turn to the resume log,
            // and a follow-up `resume=<that-id>` errors with "No
            // conversation found …" or replays a corrupt state. Forces
            // the next send to start a fresh CLI session.
            claudeSessionID = nil
        case .userText, .toolUse, .toolResult, .fileWritten:
            events.append(event)
        }
        Task { await persist() }
    }

    /// Scope the lookup to the current turn so a tool-only turn (no
    /// assistant reply) doesn't re-commit a previous turn's reply.
    private func recordStreamedAssistantTextIntoHistory() {
        var turnStart = events.startIndex
        for (index, event) in events.enumerated().reversed() {
            if case .userText = event {
                turnStart = index + 1
                break
            }
        }
        guard turnStart <= events.endIndex else { return }
        for event in events[turnStart...].reversed() {
            if case .assistantText(_, _, let text) = event, !text.isEmpty {
                let alreadyRecorded = history.last?.role == "assistant"
                    && history.last?.content == text
                if !alreadyRecorded {
                    history.append(.init(role: "assistant", content: text))
                }
                return
            }
        }
    }

    // MARK: - Persistence

    private func persist() async {
        guard !events.isEmpty || !history.isEmpty else { return }
        let record = AgentSessionRecord(
            id: sessionID,
            title: sessionTitle ?? Self.fallbackTitle,
            createdAt: sessionCreatedAt,
            lastModifiedAt: Date(),
            target: target,
            events: events,
            history: history,
            lastWorkdir: lastWorkdir,
            generatedFiles: generatedFiles,
            claudeSessionID: claudeSessionID,
            selectedModel: selectedModel,
            sessionUsage: sessionUsage == .zero ? nil : sessionUsage
        )
        await store.save(record)
    }

    private static let fallbackTitle = "Untitled session"

    private static func deriveTitle(from prompt: String) -> String {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        let collapsed = trimmed.replacingOccurrences(of: "\n", with: " ")
        if collapsed.count <= 60 { return collapsed }
        return String(collapsed.prefix(57)) + "…"
    }
}
