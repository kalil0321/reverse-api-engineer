import Foundation
import ReverseAPIProxy

struct TrafficFilter: Equatable {
    var search: String = ""
    var hosts: Set<String> = []
    var methods: Set<String> = []
    var statusBuckets: Set<StatusBucket> = []
    var onlyErrors: Bool = false

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
        if !search.isEmpty {
            let haystack = "\(flow.method) \(flow.url)".lowercased()
            if !haystack.contains(search.lowercased()) { return false }
        }
        if !hosts.isEmpty, !hosts.contains(flow.host) { return false }
        if !methods.isEmpty, !methods.contains(flow.method) { return false }
        if !statusBuckets.isEmpty {
            guard let status = flow.responseStatus else { return false }
            if !statusBuckets.contains(where: { $0.contains(status) }) { return false }
        }
        return true
    }
}
