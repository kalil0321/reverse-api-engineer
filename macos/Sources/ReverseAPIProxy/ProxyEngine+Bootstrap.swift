import Foundation

extension ProxyEngine {
    public static func bootstrap(
        applicationSupportURL: URL,
        port: Int = 8888,
        bus: FlowBus = FlowBus()
    ) throws -> ProxyEngine {
        let store = try CAStore(applicationSupportURL: applicationSupportURL)
        let root = try store.loadOrCreate()
        return try ProxyEngine(root: root, port: port, bus: bus)
    }

    public func rootDERBytes() throws -> Data {
        Data(try root.derBytes())
    }

    public func rootPEM() throws -> String {
        try root.pem()
    }
}
