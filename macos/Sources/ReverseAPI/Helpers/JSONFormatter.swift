import Foundation

enum JSONFormatter {
    static func prettyPrintJSON(_ data: Data, contentType: String?) -> String? {
        if let contentType, !contentType.lowercased().contains("json") {
            if !looksLikeJSON(data) { return nil }
        }
        guard !data.isEmpty else { return nil }
        do {
            let object = try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
            let prettified = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
            return String(data: prettified, encoding: .utf8)
        } catch {
            return nil
        }
    }

    private static func looksLikeJSON(_ data: Data) -> Bool {
        guard let first = data.first(where: { !($0 == 0x20 || $0 == 0x09 || $0 == 0x0A || $0 == 0x0D) }) else {
            return false
        }
        return first == 0x7B || first == 0x5B
    }
}
