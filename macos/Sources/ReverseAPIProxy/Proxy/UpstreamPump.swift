import Foundation
import NIOConcurrencyHelpers
import NIOCore
import NIOPosix
import NIOHTTP1
import NIOSSL

enum UpstreamError: Error {
    case connectionClosed
}

actor UpstreamPump {
    private let group: EventLoopGroup
    private let logger: AppLogger

    init(group: EventLoopGroup, logger: AppLogger) {
        self.group = group
        self.logger = logger
    }

    func forward(
        scheme: CapturedFlow.Scheme,
        host: String,
        port: Int,
        method: HTTPMethod,
        uri: String,
        headers: HTTPHeaders,
        body: ByteBuffer,
        downstream: Channel,
        initialFlow: CapturedFlow,
        maxCaptureBodyBytes: Int
    ) async throws -> CapturedFlow {
        let forwarder = StreamingResponseForwarder(
            downstream: downstream,
            initialFlow: initialFlow,
            maxCaptureBodyBytes: maxCaptureBodyBytes
        )
        let resultTask = Task { try await forwarder.awaitResponse() }

        let bootstrap = ClientBootstrap(group: group)
            .channelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)

        let channel: Channel
        do {
            channel = try await bootstrap.connect(host: host, port: port).get()
        } catch {
            forwarder.cancel(with: error)
            resultTask.cancel()
            throw error
        }

        do {
            if scheme == .https {
                try await channel.eventLoop.submit {
                    var clientConfig = TLSConfiguration.makeClientConfiguration()
                    clientConfig.applicationProtocols = ["http/1.1"]
                    let sslContext = try NIOSSLContext(configuration: clientConfig)
                    let sslHandler = try NIOSSLClientHandler(context: sslContext, serverHostname: host)
                    try channel.pipeline.syncOperations.addHandler(sslHandler, position: .first)
                }.get()
            }

            try await channel.pipeline.addHTTPClientHandlers().get()
            try await channel.pipeline.addHandler(forwarder).get()

            var requestHeaders = headers
            requestHeaders.replaceOrAdd(name: "Host", value: hostHeaderValue(host: host, port: port, scheme: scheme))
            requestHeaders.replaceOrAdd(name: "Connection", value: "close")
            requestHeaders.remove(name: "Proxy-Connection")

            let head = HTTPRequestHead(
                version: .http1_1,
                method: method,
                uri: uri,
                headers: requestHeaders
            )

            channel.write(HTTPClientRequestPart.head(head), promise: nil)
            if body.readableBytes > 0 {
                channel.write(HTTPClientRequestPart.body(.byteBuffer(body)), promise: nil)
            }
            try await channel.writeAndFlush(HTTPClientRequestPart.end(nil)).get()
        } catch {
            forwarder.cancel(with: error)
            try? await channel.close().get()
            throw error
        }

        do {
            let flow = try await resultTask.value
            try? await channel.close().get()
            return flow
        } catch {
            try? await channel.close().get()
            throw error
        }
    }
    private func hostHeaderValue(host: String, port: Int, scheme: CapturedFlow.Scheme) -> String {
        let bracketed = host.contains(":") && !host.hasPrefix("[") ? "[\(host)]" : host
        switch (scheme, port) {
        case (.http, 80), (.https, 443): return bracketed
        default: return "\(bracketed):\(port)"
        }
    }
}

private final class StreamingResponseForwarder: ChannelInboundHandler, @unchecked Sendable {
    typealias InboundIn = HTTPClientResponsePart

    private struct State {
        var flow: CapturedFlow
        var body: ByteBuffer = ByteBufferAllocator().buffer(capacity: 0)
        var continuation: CheckedContinuation<CapturedFlow, Error>?
        var result: Result<CapturedFlow, Error>?
        var settled = false
        var capturedBytes = 0
    }

    private let downstream: Channel
    private let maxCaptureBodyBytes: Int
    private let lock: NIOLockedValueBox<State>

    init(downstream: Channel, initialFlow: CapturedFlow, maxCaptureBodyBytes: Int) {
        self.downstream = downstream
        self.maxCaptureBodyBytes = max(1024, maxCaptureBodyBytes)
        self.lock = NIOLockedValueBox(State(flow: initialFlow))
    }

    func awaitResponse() async throws -> CapturedFlow {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<CapturedFlow, Error>) in
            let pending: Result<CapturedFlow, Error>? = lock.withLockedValue { state in
                if state.settled, let result = state.result {
                    return result
                }
                state.continuation = continuation
                return nil
            }
            if let pending {
                switch pending {
                case .success(let value): continuation.resume(returning: value)
                case .failure(let error): continuation.resume(throwing: error)
                }
            }
        }
    }

    func cancel(with error: Error) {
        finish(.failure(error))
    }

    func channelRead(context: ChannelHandlerContext, data: NIOAny) {
        switch unwrapInboundIn(data) {
        case .head(let head):
            lock.withLockedValue { state in
                state.flow.responseStatus = Int(head.status.code)
                state.flow.responseHeaders = head.headers.map { HTTPHeader($0.name, $0.value) }
            }

            var responseHead = HTTPResponseHead(version: head.version, status: head.status, headers: head.headers)
            responseHead.headers.replaceOrAdd(name: "Connection", value: "close")
            downstream.eventLoop.execute {
                self.downstream.write(HTTPServerResponsePart.head(responseHead), promise: nil)
            }

        case .body(let buffer):
            lock.withLockedValue { state in
                let remaining = maxCaptureBodyBytes - state.capturedBytes
                guard remaining > 0 else { return }
                var copy = buffer
                let captureLength = min(copy.readableBytes, remaining)
                if var slice = copy.readSlice(length: captureLength) {
                    state.body.writeBuffer(&slice)
                    state.capturedBytes += captureLength
                }
            }

            downstream.eventLoop.execute {
                self.downstream.write(HTTPServerResponsePart.body(.byteBuffer(buffer)), promise: nil)
            }

        case .end:
            let flow = lock.withLockedValue { state -> CapturedFlow in
                var finished = state.flow
                finished.responseBody = Data(buffer: state.body)
                finished.finishedAt = Date()
                return finished
            }
            downstream.eventLoop.execute {
                self.downstream.writeAndFlush(HTTPServerResponsePart.end(nil)).whenComplete { _ in
                    self.downstream.close(promise: nil)
                }
            }
            finish(.success(flow))
        }
    }

    func errorCaught(context: ChannelHandlerContext, error: Error) {
        finish(.failure(error))
        downstream.eventLoop.execute {
            self.downstream.close(promise: nil)
        }
        context.close(promise: nil)
    }

    func channelInactive(context: ChannelHandlerContext) {
        finish(.failure(UpstreamError.connectionClosed))
    }

    private func finish(_ result: Result<CapturedFlow, Error>) {
        let pending: CheckedContinuation<CapturedFlow, Error>? = lock.withLockedValue { state in
            if state.settled { return nil }
            state.settled = true
            state.result = result
            let cont = state.continuation
            state.continuation = nil
            return cont
        }
        switch result {
        case .success(let value): pending?.resume(returning: value)
        case .failure(let error): pending?.resume(throwing: error)
        }
    }
}
