import Foundation
import NIOSSL

actor TLSContextFactory {
    private let leafFactory: LeafCertificateFactory
    private var cache: [String: NIOSSLContext] = [:]

    init(leafFactory: LeafCertificateFactory) {
        self.leafFactory = leafFactory
    }

    func serverContext(for host: String) async throws -> NIOSSLContext {
        if let cached = cache[host] { return cached }
        let materials = try await leafFactory.materials(for: host)
        var config = TLSConfiguration.makeServerConfiguration(
            certificateChain: [.certificate(materials.certificate)],
            privateKey: .privateKey(materials.privateKey)
        )
        config.minimumTLSVersion = .tlsv12
        let context = try NIOSSLContext(configuration: config)
        cache[host] = context
        return context
    }
}
