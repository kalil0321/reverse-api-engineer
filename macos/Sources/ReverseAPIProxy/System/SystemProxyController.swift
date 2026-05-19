import Foundation

public enum SystemProxyError: Error {
    case networksetupFailed(Int32, String)
    case noNetworkServices
    case invalidHost(String)
    case invalidPort(Int)
}

public struct ProxyServiceSnapshot: Sendable, Equatable {
    public let service: String
    public let httpEnabled: Bool
    public let httpHost: String
    public let httpPort: Int
    public let httpsEnabled: Bool
    public let httpsHost: String
    public let httpsPort: Int
}

public final class SystemProxyController: @unchecked Sendable {
    private let networksetup = "/usr/sbin/networksetup"

    public init() {}

    public func enable(host: String, port: Int) throws {
        try validate(host: host, port: port)
        let services = try listNetworkServices()
        guard !services.isEmpty else { throw SystemProxyError.noNetworkServices }
        for service in services {
            try shell(networksetup, "-setwebproxy", service, host, String(port))
            try shell(networksetup, "-setsecurewebproxy", service, host, String(port))
            try shell(networksetup, "-setwebproxystate", service, "on")
            try shell(networksetup, "-setsecurewebproxystate", service, "on")
        }
    }

    public func disable() throws {
        let services = try listNetworkServices()
        guard !services.isEmpty else { return }
        for service in services {
            try shell(networksetup, "-setwebproxystate", service, "off")
            try shell(networksetup, "-setsecurewebproxystate", service, "off")
        }
    }

    public func disable(host: String, port: Int) throws {
        try validate(host: host, port: port)
        let services = try listNetworkServices()
        guard !services.isEmpty else { return }
        for service in services {
            let http = try parseGetWebProxy(service: service, command: "-getwebproxy")
            let https = try parseGetWebProxy(service: service, command: "-getsecurewebproxy")
            if http.enabled, http.host == host, http.port == port {
                try shell(networksetup, "-setwebproxystate", service, "off")
            }
            if https.enabled, https.host == host, https.port == port {
                try shell(networksetup, "-setsecurewebproxystate", service, "off")
            }
        }
    }

    public func restore(_ snapshots: [ProxyServiceSnapshot]) throws {
        for snapshot in snapshots {
            try shell(networksetup, "-setwebproxy", snapshot.service, snapshot.httpHost, String(snapshot.httpPort))
            try shell(networksetup, "-setsecurewebproxy", snapshot.service, snapshot.httpsHost, String(snapshot.httpsPort))
            try shell(networksetup, "-setwebproxystate", snapshot.service, snapshot.httpEnabled ? "on" : "off")
            try shell(networksetup, "-setsecurewebproxystate", snapshot.service, snapshot.httpsEnabled ? "on" : "off")
        }
    }

    public func snapshot() throws -> [ProxyServiceSnapshot] {
        try listNetworkServices().map { service in
            let http = try parseGetWebProxy(service: service, command: "-getwebproxy")
            let https = try parseGetWebProxy(service: service, command: "-getsecurewebproxy")
            return ProxyServiceSnapshot(
                service: service,
                httpEnabled: http.enabled,
                httpHost: http.host,
                httpPort: http.port,
                httpsEnabled: https.enabled,
                httpsHost: https.host,
                httpsPort: https.port
            )
        }
    }

    public func isEnabled() throws -> Bool {
        let services = try listNetworkServices()
        for service in services {
            let http = try shell(networksetup, "-getwebproxy", service)
            let https = try shell(networksetup, "-getsecurewebproxy", service)
            if http.contains("Enabled: Yes") && https.contains("Enabled: Yes") {
                return true
            }
        }
        return false
    }

    public func isEnabled(host: String, port: Int) throws -> Bool {
        try validate(host: host, port: port)
        let services = try listNetworkServices()
        for service in services {
            let http = try parseGetWebProxy(service: service, command: "-getwebproxy")
            let https = try parseGetWebProxy(service: service, command: "-getsecurewebproxy")
            if http.enabled,
               https.enabled,
               http.host == host,
               https.host == host,
               http.port == port,
               https.port == port {
                return true
            }
        }
        return false
    }

    public func listNetworkServices() throws -> [String] {
        let output = try shell(networksetup, "-listallnetworkservices")
        return output
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .filter { line in
                guard !line.isEmpty else { return false }
                if line.hasPrefix("An asterisk") { return false }
                if line.hasPrefix("*") { return false }
                return true
            }
    }

    internal struct GetWebProxyResult {
        let enabled: Bool
        let host: String
        let port: Int
    }

    internal static func parse(getWebProxyOutput output: String) -> GetWebProxyResult {
        var enabled = false
        var host = ""
        var port = 0
        for line in output.split(whereSeparator: \.isNewline) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("Enabled:") {
                enabled = trimmed.contains("Yes")
            } else if trimmed.hasPrefix("Server:") {
                host = String(trimmed.dropFirst("Server:".count)).trimmingCharacters(in: .whitespaces)
            } else if trimmed.hasPrefix("Port:") {
                port = Int(trimmed.dropFirst("Port:".count).trimmingCharacters(in: .whitespaces)) ?? 0
            }
        }
        return GetWebProxyResult(enabled: enabled, host: host, port: port)
    }

    private func parseGetWebProxy(service: String, command: String) throws -> GetWebProxyResult {
        let output = try shell(networksetup, command, service)
        return Self.parse(getWebProxyOutput: output)
    }

    private func validate(host: String, port: Int) throws {
        guard HostPort.validPortRange.contains(port) else { throw SystemProxyError.invalidPort(port) }
        let forbidden = CharacterSet(charactersIn: " \t\n\r'\"`\\$;&|<>")
        if host.rangeOfCharacter(from: forbidden) != nil || host.isEmpty {
            throw SystemProxyError.invalidHost(host)
        }
    }

    @discardableResult
    private func shell(_ executable: String, _ arguments: String...) throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe
        try process.run()
        process.waitUntilExit()
        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        let stdout = String(decoding: outData, as: UTF8.self)
        let stderr = String(decoding: errData, as: UTF8.self)
        guard process.terminationStatus == 0 else {
            throw SystemProxyError.networksetupFailed(process.terminationStatus, stderr.isEmpty ? stdout : stderr)
        }
        return stdout
    }

    internal func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
