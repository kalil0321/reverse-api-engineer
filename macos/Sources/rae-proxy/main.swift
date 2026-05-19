import Foundation
import ReverseAPIProxy

@main
struct RAEProxyCLI {
    static func main() async {
        let logger = AppLogger("cli")
        do {
            let options = try CLIOptions.parse()
            let store = RootCertificateStore(directory: try options.dataDirectory())
            let root = try store.loadOrCreate()

            let engine = try ProxyEngine(root: root, port: options.port)
            try await engine.start()

            print("Proxy listening on 127.0.0.1:\(options.port)")
            print("CA stored at:", store.certificateURL.path)
            print("Curl smoke test:", "curl -k -x http://127.0.0.1:\(options.port) https://example.com")
            print("Press Ctrl-C to stop.")
            fflush(stdout)

            if options.trustCA {
                Task.detached {
                    trustRoot(at: store.certificateURL)
                }
            }
            if options.launchChrome {
                launchChrome(port: options.port, dataDirectory: store.directory)
            } else {
                print("Chrome launch disabled. Pass --launch-chrome to open an isolated capture browser.")
            }

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
            fputs("fatal: \(error)\n", stderr)
            exit(1)
        }
    }

    private static func trustRoot(at certificateURL: URL) {
        #if os(macOS)
        let home = FileManager.default.homeDirectoryForCurrentUser
        let keychain = home.appendingPathComponent("Library/Keychains/login.keychain-db")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = [
            "add-trusted-cert",
            "-d",
            "-r",
            "trustRoot",
            "-k",
            keychain.path,
            certificateURL.path,
        ]
        process.standardOutput = Pipe()
        process.standardError = Pipe()

        do {
            try process.run()
            DispatchQueue.global().asyncAfter(deadline: .now() + .seconds(10)) {
                if process.isRunning {
                    process.terminate()
                }
            }
            process.waitUntilExit()
            if process.terminationStatus == 0 {
                print("Root CA trusted in login keychain.")
            } else {
                print("Could not trust the Root CA in the login keychain.")
            }
        } catch {
            print("Could not trust the Root CA: \(error)")
        }
        #else
        print("CA trust installation is only supported on macOS.")
        #endif
    }

    private static func launchChrome(port: Int, dataDirectory: URL) {
        #if os(macOS)
        guard let chromeURL = chromeExecutableURL() else {
            print("Chrome not found. Install Google Chrome or pass --no-launch-chrome and configure your own client.")
            return
        }

        let profileURL = dataDirectory.appendingPathComponent("ChromeProfile", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: profileURL, withIntermediateDirectories: true)
        } catch {
            print("Could not create Chrome profile directory: \(error)")
            return
        }

        let process = Process()
        process.executableURL = chromeURL
        process.arguments = [
            "--user-data-dir=\(profileURL.path)",
            "--proxy-server=http://127.0.0.1:\(port)",
            "--ignore-certificate-errors",
            "--no-first-run",
            "--no-default-browser-check",
            "https://example.com",
        ]

        do {
            try process.run()
            print("Opened isolated Chrome capture profile.")
        } catch {
            print("Could not launch Chrome: \(error)")
        }
        #else
        print("Chrome auto-launch is only supported on macOS.")
        #endif
    }

    private static func chromeExecutableURL() -> URL? {
        let fileManager = FileManager.default
        let candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "\(NSHomeDirectory())/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        return candidates.map { URL(fileURLWithPath: $0) }.first { fileManager.isExecutableFile(atPath: $0.path) }
    }
}

private struct CLIOptions {
    var port: Int
    var trustCA: Bool
    var launchChrome: Bool
    var dataDirectoryOverride: URL?

    static func parse(
        arguments: [String] = Array(ProcessInfo.processInfo.arguments.dropFirst()),
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws -> CLIOptions {
        var port = environment["RAE_PROXY_PORT"].flatMap(Int.init) ?? 8888
        var trustCA = environment["RAE_PROXY_TRUST_CA"].map(isTruthy) ?? false
        var launchChrome = environment["RAE_PROXY_LAUNCH_CHROME"].map(isTruthy) ?? true
        var dataDirectory = environment["RAE_PROXY_DATA_DIR"].map { URL(fileURLWithPath: $0, isDirectory: true) }

        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            switch argument {
            case "--trust-ca":
                trustCA = true
            case "--no-trust-ca":
                trustCA = false
            case "--launch-chrome":
                launchChrome = true
            case "--no-launch-chrome":
                launchChrome = false
            case "--port":
                guard let value = iterator.next(), let parsed = Int(value), HostPort.validPortRange.contains(parsed) else {
                    throw CLIError.invalidOption("--port requires a value from 1 to 65535")
                }
                port = parsed
            case "--data-dir":
                guard let value = iterator.next(), !value.isEmpty else {
                    throw CLIError.invalidOption("--data-dir requires a path")
                }
                dataDirectory = URL(fileURLWithPath: value, isDirectory: true)
            default:
                throw CLIError.invalidOption("unknown option \(argument)")
            }
        }

        guard HostPort.validPortRange.contains(port) else {
            throw CLIError.invalidOption("port must be from 1 to 65535")
        }

        return CLIOptions(port: port, trustCA: trustCA, launchChrome: launchChrome, dataDirectoryOverride: dataDirectory)
    }

    func dataDirectory() throws -> URL {
        if let dataDirectoryOverride {
            return dataDirectoryOverride
        }
        return try RootCertificateStore.defaultDirectory()
    }

    private static func isTruthy(_ value: String) -> Bool {
        ["1", "true", "yes", "on"].contains(value.lowercased())
    }
}

private enum CLIError: Error, CustomStringConvertible {
    case invalidOption(String)

    var description: String {
        switch self {
        case .invalidOption(let message):
            return message
        }
    }
}
