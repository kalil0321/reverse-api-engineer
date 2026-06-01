import Foundation

actor AgentClient {
    enum ClientError: Error {
        case notConnected
        case encodingFailed
    }

    private var task: URLSessionWebSocketTask?
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func connect(port: Int) async throws {
        if let existing = task, isLive(existing) { return }
        if task != nil { disconnect() }
        let url = URL(string: "ws://127.0.0.1:\(port)")!
        let webSocketTask = session.webSocketTask(with: url)
        webSocketTask.resume()
        self.task = webSocketTask
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    func send(_ request: AgentChatRequest) async throws {
        guard let task else { throw ClientError.notConnected }
        let data = try JSONEncoder().encode(request)
        guard let json = String(data: data, encoding: .utf8) else {
            throw ClientError.encodingFailed
        }
        try await task.send(.string(json))
    }

    func cancel(_ request: AgentCancelRequest) async throws {
        guard let task else { throw ClientError.notConnected }
        let data = try JSONEncoder().encode(request)
        guard let json = String(data: data, encoding: .utf8) else {
            throw ClientError.encodingFailed
        }
        try await task.send(.string(json))
    }

    func events() -> AsyncThrowingStream<AgentEvent, Error> {
        AsyncThrowingStream<AgentEvent, Error> { continuation in
            let receiveTask = Task {
                do {
                    while true {
                        try Task.checkCancellation()
                        guard let task = self.task else {
                            continuation.finish()
                            return
                        }
                        let message = try await task.receive()
                        let data: Data
                        switch message {
                        case .data(let raw):
                            data = raw
                        case .string(let string):
                            data = Data(string.utf8)
                        @unknown default:
                            continue
                        }
                        let event = try AgentEventDecoder.decode(data)
                        continuation.yield(event)
                    }
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                receiveTask.cancel()
            }
        }
    }

    private nonisolated func isLive(_ task: URLSessionWebSocketTask) -> Bool {
        task.state == .running
    }
}
