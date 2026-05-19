import Foundation
import ReverseAPIProxy

@main
struct RAEProxyCLI {
    static func main() async {
        let logger = AppLogger("cli")
        do {
            logger.info("Generating root CA…")
            let root = try CertificateAuthority.generateRoot()
            let port = ProcessInfo.processInfo.environment["RAE_PROXY_PORT"].flatMap(Int.init) ?? 8888

            let engine = try ProxyEngine(root: root, port: port)
            try await engine.start()

            let pem = try root.pem()
            let pemURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("reverseapi-root.pem")
            try pem.write(to: pemURL, atomically: true, encoding: .utf8)
            print("Root CA PEM written to:", pemURL.path)
            print("Install with: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain", pemURL.path)
            print("Set proxy on localhost:\(port) (HTTP + HTTPS) to capture.")
            print("Press Ctrl-C to stop.")

            let bus = engine.bus
            Task {
                for await event in await bus.subscribe() {
                    switch event {
                    case .started(let flow):
                        print("→ \(flow.method) \(flow.url)")
                    case .updated:
                        break
                    case .finished(let flow):
                        let status = flow.responseStatus.map(String.init) ?? "ERR"
                        let bytes = flow.responseBody.count
                        if let error = flow.error {
                            print("✗ \(flow.method) \(flow.url) — \(error)")
                        } else {
                            print("← \(status) \(flow.method) \(flow.url) (\(bytes) B)")
                        }
                    }
                }
            }

            try await Task.sleep(for: .seconds(60 * 60 * 24 * 365))
            try await engine.stop()
        } catch {
            logger.error("fatal: \(error)")
            exit(1)
        }
    }
}
