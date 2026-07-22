import Foundation
import NIOCore
import NIOPosix
import NIOHTTP1

public final class ProxyEngine: @unchecked Sendable {
    public let port: Int
    public let bus: FlowBus
    public let root: RootCertificate

    private let leafFactory: LeafCertificateFactory
    private let tlsContexts: TLSContextFactory
    private let upstream: UpstreamPump
    private let logger = AppLogger("proxy.engine")
    private let group: MultiThreadedEventLoopGroup

    private var serverChannel: Channel?

    public init(root: RootCertificate, port: Int = 8888, bus: FlowBus = FlowBus()) throws {
        self.root = root
        self.port = port
        self.bus = bus
        self.leafFactory = try LeafCertificateFactory(root: root)
        self.tlsContexts = TLSContextFactory(leafFactory: leafFactory)
        self.group = MultiThreadedEventLoopGroup(numberOfThreads: System.coreCount)
        self.upstream = UpstreamPump(group: group, logger: AppLogger("proxy.upstream"))
    }

    public var isRunning: Bool { serverChannel != nil }

    public func start(host: String = "127.0.0.1") async throws {
        guard serverChannel == nil else { return }
        let proxyContext = ProxyContext(tlsContexts: tlsContexts, upstream: upstream, bus: bus, logger: AppLogger("proxy.handler"))

        let bootstrap = ServerBootstrap(group: group)
            .serverChannelOption(ChannelOptions.backlog, value: 256)
            .serverChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
            .childChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
            .childChannelOption(ChannelOptions.allowRemoteHalfClosure, value: true)
            .childChannelInitializer { channel in
                let decoder = ByteToMessageHandler(HTTPRequestDecoder(leftOverBytesStrategy: .forwardBytes))
                let encoder = HTTPResponseEncoder()
                let proxy = ProxyHandler(context: proxyContext, mode: .entry)
                do {
                    try channel.pipeline.syncOperations.addHandler(decoder, name: PipelineNames.decoder)
                    try channel.pipeline.syncOperations.addHandler(encoder, name: PipelineNames.encoder)
                    try channel.pipeline.syncOperations.addHandler(proxy, name: PipelineNames.proxy)
                    return channel.eventLoop.makeSucceededVoidFuture()
                } catch {
                    return channel.eventLoop.makeFailedFuture(error)
                }
            }

        let channel = try await bootstrap.bind(host: host, port: port).get()
        serverChannel = channel
        logger.info("proxy listening on \(host):\(port)")
    }

    /// Stop listening but keep the event-loop group alive so capture can be
    /// started again on the same engine. The group is only torn down in
    /// ``terminate()`` — shutting it down here would leave the group in a
    /// permanently-shutdown state, so the next ``start()`` on this engine (a
    /// capture toggle-off/on, or the cleanup after a failed start) would fail
    /// with `EventLoopError.shutdown`.
    public func stop() async throws {
        guard let channel = serverChannel else { return }
        serverChannel = nil
        do {
            try await channel.close().get()
            logger.info("proxy stopped")
        } catch ChannelError.alreadyClosed {
            logger.info("proxy channel already closed")
        }
    }

    /// Final teardown: stop listening, then shut down the event-loop group.
    /// After this the engine cannot be restarted; call it only on app exit.
    public func terminate() async throws {
        var stopError: Error?
        do {
            try await stop()
        } catch {
            stopError = error
        }
        do {
            try await group.shutdownGracefully()
        } catch {
            logger.error("event-loop shutdown failed: \(error)")
            if stopError == nil { throw error }
        }
        if let stopError { throw stopError }
        logger.info("proxy terminated")
    }
}
