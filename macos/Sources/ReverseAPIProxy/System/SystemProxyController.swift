import Foundation

public enum SystemProxyError: Error {
    case scriptFailed(String)
    case networksetupFailed(Int32, String)
    case noNetworkServices
}

public final class SystemProxyController: @unchecked Sendable {
    private let networksetup = "/usr/sbin/networksetup"

    public init() {}

    public func enable(host: String, port: Int) throws {
        let services = try listNetworkServices()
        guard !services.isEmpty else { throw SystemProxyError.noNetworkServices }
        let commands = services.flatMap { service -> [String] in
            let q = shellQuote(service)
            return [
                "\(networksetup) -setwebproxy \(q) \(host) \(port)",
                "\(networksetup) -setsecurewebproxy \(q) \(host) \(port)",
                "\(networksetup) -setwebproxystate \(q) on",
                "\(networksetup) -setsecurewebproxystate \(q) on",
            ]
        }
        try runWithAdminPrivileges(commands.joined(separator: " && "))
    }

    public func disable() throws {
        let services = try listNetworkServices()
        guard !services.isEmpty else { return }
        let commands = services.flatMap { service -> [String] in
            let q = shellQuote(service)
            return [
                "\(networksetup) -setwebproxystate \(q) off",
                "\(networksetup) -setsecurewebproxystate \(q) off",
            ]
        }
        try runWithAdminPrivileges(commands.joined(separator: " && "))
    }

    public func isEnabled() throws -> Bool {
        let services = try listNetworkServices()
        for service in services {
            let output = try shell(networksetup, "-getwebproxy", service)
            if output.contains("Enabled: Yes") { return true }
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

    private func runWithAdminPrivileges(_ command: String) throws {
        let escaped = command
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let script = "do shell script \"\(escaped)\" with administrator privileges"
        var error: NSDictionary?
        if let apple = NSAppleScript(source: script) {
            apple.executeAndReturnError(&error)
        } else {
            throw SystemProxyError.scriptFailed("failed to construct script")
        }
        if let error {
            let message = error[NSAppleScript.errorMessage] as? String ?? "\(error)"
            throw SystemProxyError.scriptFailed(message)
        }
    }

    private func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
