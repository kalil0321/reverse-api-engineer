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
        history.append(.init(role: "user", content: trimmed))
        let request = AgentChatRequest(
            id: UUID().uuidString,
            message: trimmed,
            target: target.rawValue,
            flows: flows.map(AgentFlowPayload.init),
            history: history
        )
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
                self.lastError = "Agent stream error: \(error)"
                self.status = .failed
            }
        }
    }

    private func handle(_ event: AgentEvent) {
        events.append(event)
        switch event {
        case .assistantText(_, _, let text):
            history.append(.init(role: "assistant", content: text))
        case .complete(_, _, let workdir, let files):
            lastWorkdir = workdir
            generatedFiles = files
            status = .ready
        case .error(_, _, let message):
            lastError = message
            status = .failed
        case .toolUse, .toolResult, .fileWritten:
            break
        }
    }
}
