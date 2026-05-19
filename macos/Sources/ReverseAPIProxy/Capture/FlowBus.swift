import Foundation

public enum FlowEvent: Sendable {
    case started(CapturedFlow)
    case updated(CapturedFlow)
    case finished(CapturedFlow)
}

public actor FlowBus {
    public typealias Stream = AsyncStream<FlowEvent>

    private var subscribers: [UUID: Stream.Continuation] = [:]

    public init() {}

    public func subscribe() -> Stream {
        let (stream, continuation) = Stream.makeStream(bufferingPolicy: .unbounded)
        let token = UUID()
        subscribers[token] = continuation
        continuation.onTermination = { [weak self] _ in
            Task { await self?.unsubscribe(token) }
        }
        return stream
    }

    public func emit(_ event: FlowEvent) {
        for continuation in subscribers.values {
            continuation.yield(event)
        }
    }

    private func unsubscribe(_ token: UUID) {
        subscribers.removeValue(forKey: token)
    }
}
