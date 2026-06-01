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

    let store: AgentSessionStore

    private let sidecar = AgentSidecar()
    private let client = AgentClient()
    private var receiverTask: Task<Void, Never>?
    private(set) var sessionID = UUID().uuidString
    private var sessionCreatedAt = Date()
    private var sessionTitle: String?
    /// SDK-assigned session id, captured on the first turn. Passed back as
    /// `resume` on subsequent sends so Claude rehydrates the conversation
    /// without us replaying `history` on every message.
    private var claudeSessionID: String?
    private let workdir: URL
    private let launchSpec: AgentSidecar.LaunchSpec

    init(workdir: URL, launchSpec: AgentSidecar.LaunchSpec? = nil) {
        self.workdir = workdir
        self.launchSpec = launchSpec ?? .python3(workdir: workdir)
        self.store = AgentSessionStore(rootDirectory: workdir)
    }

    // MARK: - Session lifecycle (list / new / load)

    /// Reset state and switch into a fresh, unsaved session. The session is
    /// only persisted to disk once the user sends their first message.
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
        if status == .failed { status = .idle }
        mode = .session
    }

    /// Load a session from disk and switch the panel to its timeline.
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
        lastError = nil
        if status == .failed { status = .idle }
        mode = .session
    }

    /// Drop back to the sessions list without clearing in-memory state.
    func backToList() {
        mode = .list
    }

    /// Delete a session permanently (from disk + the store's index). If the
    /// currently open session is the one being deleted, also reset memory.
    func deleteSession(id: String) async {
        if sessionID == id {
            startNewSession()
            mode = .list
        }
        await store.delete(id: id)
    }

    // MARK: - Existing API

    func ensureRunning() async {
        switch status {
        case .ready, .streaming, .launching:
            return
        case .idle, .failed:
            break
        }
        status = .launching
        do {
            let port = try await sidecar.launch(launchSpec)
            try await client.connect(port: port)
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
        // Once the SDK has assigned us a session id, lean on `resume` and
        // skip shipping our own history — the SDK reattaches to its
        // persisted conversation state instead.
        let historyToSend: [AgentHistoryItem] = claudeSessionID == nil ? history : []
        let request = AgentChatRequest(
            id: sessionID,
            message: trimmed,
            target: target.rawValue,
            flows: flows.map { AgentFlowPayload($0) },
            history: historyToSend,
            claudeSessionId: claudeSessionID
        )
        history.append(userHistoryItem)
        events.append(.userText(eventID: UUID(), text: trimmed))
        // Auto-derive a title from the first user prompt so the sessions
        // list shows something meaningful instead of a UUID.
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

    /// Clear the active conversation in memory. Doesn't touch disk — the
    /// previous session record stays on disk until the user explicitly
    /// deletes it from the list.
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
            // Don't surface as a timeline row; just remember the id so the
            // next send can pass it as `resume`.
            if !claudeID.isEmpty { claudeSessionID = claudeID }
        case .userText, .toolUse, .toolResult, .fileWritten:
            events.append(event)
        }
        Task { await persist() }
    }

    /// Walk back from the timeline tail only as far as the most recent
    /// `userText` event — that's where the current turn started. If the
    /// turn ended without an assistant reply (tool-only turn, error, etc.)
    /// we do nothing instead of re-committing a previous turn's reply, which
    /// was the bug in the un-scoped version.
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

    /// Snapshot the current in-memory session and write it to disk. Cheap
    /// (the whole record is just a handful of fields plus the events array)
    /// so we can call this after every event without buffering.
    private func persist() async {
        // Don't bother saving an empty, never-used session — it would just
        // clutter the list with no-op entries on every app launch.
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
            claudeSessionID: claudeSessionID
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
