import Foundation

public struct HostPort: Sendable, Hashable {
    public let host: String
    public let port: Int

    public init(host: String, port: Int) {
        self.host = host
        self.port = port
    }

    public static func parseAuthority(_ string: String) -> HostPort? {
        if string.hasPrefix("[") {
            guard let close = string.firstIndex(of: "]") else { return nil }
            let host = String(string[string.index(after: string.startIndex)..<close])
            let rest = string[string.index(after: close)...]
            if rest.isEmpty { return HostPort(host: host, port: 443) }
            guard rest.first == ":", let port = Int(rest.dropFirst()) else { return nil }
            return HostPort(host: host, port: port)
        }
        let parts = string.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        guard let hostPart = parts.first, !hostPart.isEmpty else { return nil }
        if parts.count == 1 {
            return HostPort(host: String(hostPart), port: 443)
        }
        guard let port = Int(parts[1]) else { return nil }
        return HostPort(host: String(hostPart), port: port)
    }

    public static func parseAbsoluteURI(_ uri: String) -> (HostPort, String, CapturedFlow.Scheme)? {
        guard let scheme = ["http://", "https://"].first(where: { uri.hasPrefix($0) }) else {
            return nil
        }
        let captured: CapturedFlow.Scheme = scheme == "https://" ? .https : .http
        let defaultPort = captured == .https ? 443 : 80
        let withoutScheme = uri.dropFirst(scheme.count)
        let pathStart = withoutScheme.firstIndex(of: "/") ?? withoutScheme.endIndex
        let authority = String(withoutScheme[..<pathStart])
        let path = pathStart == withoutScheme.endIndex ? "/" : String(withoutScheme[pathStart...])
        guard var hp = HostPort.parseAuthority(authority) else { return nil }
        if !authority.contains(":") {
            hp = HostPort(host: hp.host, port: defaultPort)
        }
        return (hp, path, captured)
    }
}
