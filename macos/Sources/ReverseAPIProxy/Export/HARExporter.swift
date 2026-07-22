import Foundation

public enum HARExporter {
    private static let dateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    public static func export(_ flows: [CapturedFlow]) throws -> Data {
        let entries = flows.map(entry(for:))
        let har: [String: Any] = [
            "log": [
                "version": "1.2",
                "creator": ["name": "rae", "version": "0.1"],
                "entries": entries,
            ]
        ]
        return try JSONSerialization.data(withJSONObject: har, options: [.prettyPrinted, .sortedKeys])
    }

    static func entry(for flow: CapturedFlow) -> [String: Any] {
        let started = Self.dateFormatter.string(from: flow.startedAt)
        let duration = ((flow.finishedAt ?? flow.startedAt).timeIntervalSince(flow.startedAt)) * 1000

        let requestContentType = header(flow.requestHeaders, "content-type")
        let responseContentType = header(flow.responseHeaders, "content-type")

        var request: [String: Any] = [
            "method": flow.method,
            "url": flow.url,
            "httpVersion": "HTTP/1.1",
            "cookies": [],
            "headers": flow.requestHeaders.map { ["name": $0.name, "value": $0.value] },
            "queryString": queryString(from: flow.path),
            "headersSize": -1,
            "bodySize": flow.requestBody.count,
        ]
        if !flow.requestBody.isEmpty {
            var postData: [String: Any] = ["mimeType": requestContentType ?? ""]
            if let text = String(data: flow.requestBody, encoding: .utf8) {
                postData["text"] = text
            } else {
                postData["encoding"] = "base64"
                postData["text"] = flow.requestBody.base64EncodedString()
            }
            request["postData"] = postData
        }

        var responseContent: [String: Any] = [
            "size": flow.responseBody.count,
            "mimeType": responseContentType ?? "",
        ]
        if !flow.responseBody.isEmpty {
            if let text = String(data: flow.responseBody, encoding: .utf8) {
                responseContent["text"] = text
            } else {
                responseContent["encoding"] = "base64"
                responseContent["text"] = flow.responseBody.base64EncodedString()
            }
        }

        var record: [String: Any] = [
            "startedDateTime": started,
            "time": duration,
            "request": request,
            "response": [
                "status": flow.responseStatus ?? 0,
                "statusText": "",
                "httpVersion": "HTTP/1.1",
                "cookies": [],
                "headers": flow.responseHeaders.map { ["name": $0.name, "value": $0.value] },
                "content": responseContent,
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": flow.responseBody.count,
            ],
            "cache": [:],
            "timings": [
                "send": 0,
                "wait": duration,
                "receive": 0,
            ],
        ]
        if let error = flow.error {
            record["_error"] = error
        }
        return record
    }

    private static func header(_ headers: [HTTPHeader], _ name: String) -> String? {
        let lower = name.lowercased()
        return headers.first(where: { $0.name.lowercased() == lower })?.value
    }

    static func queryString(from path: String) -> [[String: String]] {
        guard let queryIndex = path.firstIndex(of: "?") else { return [] }
        let rawQuery = path[path.index(after: queryIndex)...]
        let query = rawQuery.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false).first ?? ""
        return query.split(separator: "&").compactMap { pair in
            let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard let name = parts.first else { return nil }
            let value = parts.count > 1 ? String(parts[1]) : ""
            return [
                "name": decodeFormComponent(String(name)),
                "value": decodeFormComponent(value),
            ]
        }
    }

    static func decodeFormComponent(_ value: String) -> String {
        let withSpaces = value.replacingOccurrences(of: "+", with: " ")
        return withSpaces.removingPercentEncoding ?? withSpaces
    }
}
