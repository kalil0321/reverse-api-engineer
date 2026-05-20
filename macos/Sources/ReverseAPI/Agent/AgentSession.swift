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

    private(set) var status: Status = .idle
    private(set) var events: [AgentEvent] = []
    private(set) var lastError: String?
    private(set) var lastWorkdir: String?
    private(set) var generatedFiles: [String] = []
    private(set) var history: [AgentHistoryItem] = []

    var input: String = ""
    var target: AgentTargetLanguage = .python

    private let sidecar = AgentSidecar()
    private let client = AgentClient()
    private var receiverTask: Task<Void, Never>?
    private var sessionID = UUID().uuidString
    private let workdir: URL
    private let launchSpec: AgentSidecar.LaunchSpec

    init(workdir: URL, launchSpec: AgentSidecar.LaunchSpec? = nil) {
        self.workdir = workdir
        self.launchSpec = launchSpec ?? .python3(workdir: workdir)
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
        let previousHistory = history
        let userHistoryItem = AgentHistoryItem(role: "user", content: trimmed)
        let request = AgentChatRequest(
            id: sessionID,
            message: trimmed,
            target: target.rawValue,
            flows: flows.map { AgentFlowPayload($0) },
            history: previousHistory
        )
        history.append(userHistoryItem)
        // Surface the user's prompt in the timeline immediately so they see
        // their own message right next to the assistant's reply, before the
        // agent has had a chance to respond.
        events.append(.userText(eventID: UUID(), text: trimmed))
        do {
            input = ""
            status = .streaming
            try await client.send(request)
        } catch {
            lastError = "Failed to send chat: \(error)"
            status = .failed
        }
    }

    func clear() {
        events.removeAll()
        history.removeAll()
        generatedFiles = []
        lastWorkdir = nil
        lastError = nil
        sessionID = UUID().uuidString
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
            // Stream the chunk into the active assistant message instead of
            // creating a new event per delta. If the previous event isn't an
            // assistantText, start a fresh one with this chunk as the seed.
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
        case .userText, .toolUse, .toolResult, .fileWritten:
            events.append(event)
        }
    }

    /// When the assistant streams its reply via chunks we only know the full
    /// text once the turn completes. Walk the timeline backwards to find the
    /// last assistantText and commit it into history (unless it's already the
    /// latest entry, which is the legacy non-streaming path).
    private func recordStreamedAssistantTextIntoHistory() {
        for event in events.reversed() {
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
}
