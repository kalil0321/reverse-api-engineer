import Foundation
import ReverseAPIProxy

struct TrafficFilter: Equatable {
    var search: String = ""
    var hosts: Set<String> = []
    var methods: Set<String> = []
    var statusBuckets: Set<StatusBucket> = []
    var resourceKinds: Set<ResourceKind> = []
    var onlyErrors: Bool = false

    enum ResourceKind: String, CaseIterable, Identifiable, Hashable {
        case document = "Doc"
        case fetch = "Fetch/XHR"
        case script = "JS"
        case stylesheet = "CSS"
        case image = "Img"
        case media = "Media"
        case font = "Font"
        case websocket = "WS"
        case other = "Other"

        var id: String { rawValue }
    }

    enum StatusBucket: String, CaseIterable, Identifiable, Hashable {
        case informational = "1xx"
        case success = "2xx"
        case redirect = "3xx"
        case clientError = "4xx"
        case serverError = "5xx"

        var id: String { rawValue }

        func contains(_ status: Int) -> Bool {
            switch self {
            case .informational: return (100..<200).contains(status)
            case .success: return (200..<300).contains(status)
            case .redirect: return (300..<400).contains(status)
            case .clientError: return (400..<500).contains(status)
            case .serverError: return (500..<600).contains(status)
            }
        }
    }

    func matches(_ flow: CapturedFlow) -> Bool {
        if onlyErrors {
            if flow.error == nil, !(flow.responseStatus.map { $0 >= 400 } ?? false) {
                return false
            }
        }
        let terms = search
            .lowercased()
            .split(whereSeparator: \.isWhitespace)
            .map(String.init)
        if !terms.isEmpty {
            let haystack = searchHaystack(for: flow)
            if !terms.allSatisfy({ haystack.contains($0) }) { return false }
        }
        if !hosts.isEmpty, !hosts.contains(flow.host) { return false }
        if !methods.isEmpty, !methods.contains(flow.method) { return false }
        if !resourceKinds.isEmpty, !resourceKinds.contains(Self.resourceKind(for: flow)) { return false }
        if !statusBuckets.isEmpty {
            guard let status = flow.responseStatus else { return false }
            if !statusBuckets.contains(where: { $0.contains(status) }) { return false }
        }
        return true
    }

    private func searchHaystack(for flow: CapturedFlow) -> String {
        var parts = [
            flow.method,
            flow.url,
            flow.host,
            flow.path,
            Self.resourceKind(for: flow).rawValue,
        ]
        if let status = flow.responseStatus {
            parts.append(String(status))
        }
        if let error = flow.error {
            parts.append(error)
        }
        parts.append(contentsOf: flow.requestHeaders.flatMap { [$0.name, $0.value] })
        parts.append(contentsOf: flow.responseHeaders.flatMap { [$0.name, $0.value] })
        return parts.joined(separator: " ").lowercased()
    }

    static func resourceKind(for flow: CapturedFlow) -> ResourceKind {
        if isWebSocket(flow) { return .websocket }

        let contentType = headerValue("content-type", in: flow.responseHeaders)?.lowercased() ?? ""
        let accept = headerValue("accept", in: flow.requestHeaders)?.lowercased() ?? ""
        let path = flow.path.lowercased()
        let ext = path
            .split(separator: "?")
            .first?
            .split(separator: "/")
            .last?
            .split(separator: ".")
            .last
            .map { String($0).lowercased() } ?? ""

        if contentType.contains("text/html") || accept.contains("text/html") || ["html", "htm"].contains(ext) {
            return .document
        }
        if contentType.contains("text/css") || ext == "css" {
            return .stylesheet
        }
        if contentType.contains("javascript") ||
            contentType.contains("ecmascript") ||
            ["js", "mjs", "cjs"].contains(ext) {
            return .script
        }
        if contentType.hasPrefix("image/") || ["png", "jpg", "jpeg", "gif", "webp", "avif", "svg", "ico"].contains(ext) {
            return .image
        }
        if contentType.hasPrefix("video/") ||
            contentType.hasPrefix("audio/") ||
            ["mp4", "webm", "mov", "m4v", "mp3", "wav", "ogg", "m3u8"].contains(ext) {
            return .media
        }
        if contentType.contains("font") || ["woff", "woff2", "ttf", "otf", "eot"].contains(ext) {
            return .font
        }
        if contentType.contains("json") ||
            contentType.contains("xml") ||
            accept.contains("application/json") ||
            path.contains("/api/") ||
            flow.method != "GET" {
            return .fetch
        }
        return .other
    }

    private static func isWebSocket(_ flow: CapturedFlow) -> Bool {
        let upgrade = headerValue("upgrade", in: flow.requestHeaders)?.lowercased()
            ?? headerValue("upgrade", in: flow.responseHeaders)?.lowercased()
        return upgrade == "websocket" || flow.responseStatus == 101
    }

    private static func headerValue(_ name: String, in headers: [HTTPHeader]) -> String? {
        headers.first { $0.name.caseInsensitiveCompare(name) == .orderedSame }?.value
    }
}
