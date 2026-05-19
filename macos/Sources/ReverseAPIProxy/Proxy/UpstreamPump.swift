import Foundation
import NIOCore
import NIOPosix
import NIOHTTP1
import NIOSSL

struct UpstreamResponse: Sendable {
    let status: HTTPResponseStatus
    let version: HTTPVersion
    let headers: HTTPHeaders
    let body: ByteBuffer
}

enum UpstreamError: Error {
    case connectionClosed
    case missingResponse
    case unexpected(String)
}

actor UpstreamPump {
    private let group: EventLoopGroup
    private let logger: AppLogger

    init(group: EventLoopGroup, logger: AppLogger) {
        self.group = group
        self.logger = logger
    }

    func send(
        scheme: CapturedFlow.Scheme,
        host: String,
        port: Int,
        method: HTTPMethod,
        uri: String,
        headers: HTTPHeaders,
        body: ByteBuffer
    ) async throws -> UpstreamResponse {
        let bootstrap = ClientBootstrap(group: group)
            .channelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)

        let channel = try await bootstrap.connect(host: host, port: port).get()

        if scheme == .https {
            let clientConfig = TLSConfiguration.makeClientConfiguration()
            let sslContext = try NIOSSLContext(configuration: clientConfig)
            let sslHandler = try NIOSSLClientHandler(context: sslContext, serverHostname: host)
            try await channel.pipeline.addHandler(sslHandler, position: .first).get()
        }

        let collector = ResponseCollector()
        try await channel.pipeline.addHTTPClientHandlers().get()
        try await channel.pipeline.addHandler(collector).get()

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

        let response = try await collector.awaitResponse()
        try? await channel.close().get()
        return response
    }

    private func hostHeaderValue(host: String, port: Int, scheme: CapturedFlow.Scheme) -> String {
        switch (scheme, port) {
        case (.http, 80), (.https, 443): return host
        default: return "\(host):\(port)"
        }
    }
}

private final class ResponseCollector: ChannelInboundHandler, @unchecked Sendable {
    typealias InboundIn = HTTPClientResponsePart

    private var head: HTTPResponseHead?
    private var body = ByteBuffer()
    private let promise: NIOLockedValueBox<CheckedContinuation<UpstreamResponse, Error>?> = .init(nil)

    func awaitResponse() async throws -> UpstreamResponse {
        try await withCheckedThrowingContinuation { continuation in
            promise.withLockedValue { $0 = continuation }
        }
    }

    func channelRead(context: ChannelHandlerContext, data: NIOAny) {
        switch unwrapInboundIn(data) {
        case .head(let head):
            self.head = head
        case .body(var buffer):
            body.writeBuffer(&buffer)
        case .end:
            finish(.success(buildResponse()))
        }
    }

    func errorCaught(context: ChannelHandlerContext, error: Error) {
        finish(.failure(error))
        context.close(promise: nil)
    }

    func channelInactive(context: ChannelHandlerContext) {
        if head == nil {
            finish(.failure(UpstreamError.connectionClosed))
        }
    }

    private func buildResponse() -> UpstreamResponse {
        let head = self.head ?? HTTPResponseHead(version: .http1_1, status: .internalServerError)
        return UpstreamResponse(status: head.status, version: head.version, headers: head.headers, body: body)
    }

    private func finish(_ result: Result<UpstreamResponse, Error>) {
        let cont = promise.withLockedValue { value -> CheckedContinuation<UpstreamResponse, Error>? in
            defer { value = nil }
            return value
        }
        switch result {
        case .success(let value): cont?.resume(returning: value)
        case .failure(let error): cont?.resume(throwing: error)
        }
    }
}
