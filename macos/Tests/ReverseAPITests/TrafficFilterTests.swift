import XCTest
import ReverseAPIProxy
@testable import ReverseAPI

final class TrafficFilterTests: XCTestCase {
    private func make(method: String = "GET", host: String = "api.example.com", path: String = "/users", status: Int? = 200, error: String? = nil) -> CapturedFlow {
        var flow = CapturedFlow(scheme: .https, method: method, host: host, port: 443, path: path)
        flow.responseStatus = status
        flow.error = error
        return flow
    }

    func testEmptyFilterMatchesEverything() {
        let filter = TrafficFilter()
        XCTAssertTrue(filter.matches(make()))
    }

    func testSearchMatchesURLSubstring() {
        var filter = TrafficFilter()
        filter.search = "users"
        XCTAssertTrue(filter.matches(make()))
        XCTAssertFalse(filter.matches(make(path: "/posts")))
    }

    func testSearchIsCaseInsensitive() {
        var filter = TrafficFilter()
        filter.search = "USERS"
        XCTAssertTrue(filter.matches(make()))
    }

    func testHostFilter() {
        var filter = TrafficFilter()
        filter.hosts = ["api.example.com"]
        XCTAssertTrue(filter.matches(make()))
        XCTAssertFalse(filter.matches(make(host: "other.com")))
    }

    func testMethodFilter() {
        var filter = TrafficFilter()
        filter.methods = ["POST"]
        XCTAssertFalse(filter.matches(make()))
        XCTAssertTrue(filter.matches(make(method: "POST")))
    }

    func testStatusBucketSuccess() {
        var filter = TrafficFilter()
        filter.statusBuckets = [.success]
        XCTAssertTrue(filter.matches(make(status: 200)))
        XCTAssertFalse(filter.matches(make(status: 404)))
    }

    func testStatusBucketClientError() {
        var filter = TrafficFilter()
        filter.statusBuckets = [.clientError]
        XCTAssertTrue(filter.matches(make(status: 404)))
        XCTAssertFalse(filter.matches(make(status: 200)))
    }

    func testOnlyErrorsFiltersBy4xxOr5xxOrError() {
        var filter = TrafficFilter()
        filter.onlyErrors = true
        XCTAssertTrue(filter.matches(make(status: 500)))
        XCTAssertTrue(filter.matches(make(status: 400)))
        XCTAssertTrue(filter.matches(make(status: nil, error: "boom")))
        XCTAssertFalse(filter.matches(make(status: 200)))
    }

    func testStatusBucketRequiresResponseStatus() {
        var filter = TrafficFilter()
        filter.statusBuckets = [.success]
        XCTAssertFalse(filter.matches(make(status: nil)))
    }

    func testStatusBucketContainsBoundaries() {
        XCTAssertTrue(TrafficFilter.StatusBucket.success.contains(200))
        XCTAssertTrue(TrafficFilter.StatusBucket.success.contains(299))
        XCTAssertFalse(TrafficFilter.StatusBucket.success.contains(300))
        XCTAssertTrue(TrafficFilter.StatusBucket.redirect.contains(301))
        XCTAssertTrue(TrafficFilter.StatusBucket.clientError.contains(404))
        XCTAssertTrue(TrafficFilter.StatusBucket.serverError.contains(503))
    }
}
