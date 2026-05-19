import XCTest
import ReverseAPIProxy
@testable import ReverseAPI

final class TrafficFilterTests: XCTestCase {
    private func make(
        method: String = "GET",
        host: String = "api.example.com",
        path: String = "/users",
        status: Int? = 200,
        error: String? = nil,
        requestHeaders: [HTTPHeader] = [],
        responseHeaders: [HTTPHeader] = []
    ) -> CapturedFlow {
        var flow = CapturedFlow(
            scheme: .https,
            method: method,
            host: host,
            port: 443,
            path: path,
            requestHeaders: requestHeaders
        )
        flow.responseStatus = status
        flow.error = error
        flow.responseHeaders = responseHeaders
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

    func testSearchMatchesStatusHostHeadersAndResourceKind() {
        let flow = make(
            host: "assets.example.com",
            path: "/styles/app.css",
            status: 304,
            responseHeaders: [HTTPHeader("Cache-Control", "max-age=3600")]
        )

        var filter = TrafficFilter()
        filter.search = "assets 304 cache css"
        XCTAssertTrue(filter.matches(flow))

        filter.search = "missing"
        XCTAssertFalse(filter.matches(flow))
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

    func testResourceKindFilterMatchesImage() {
        var filter = TrafficFilter()
        filter.resourceKinds = [.image]
        XCTAssertTrue(filter.matches(make(path: "/logo.png")))
        XCTAssertTrue(filter.matches(make(responseHeaders: [HTTPHeader("Content-Type", "image/webp")])))
        XCTAssertFalse(filter.matches(make(responseHeaders: [HTTPHeader("Content-Type", "text/css")])))
    }

    func testResourceKindClassifiesStylesheetsAndScripts() {
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(path: "/app.css")), .stylesheet)
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(path: "/app.js")), .script)
        XCTAssertEqual(
            TrafficFilter.resourceKind(for: make(responseHeaders: [HTTPHeader("Content-Type", "text/javascript")])),
            .script
        )
    }

    func testResourceKindClassifiesFetch() {
        XCTAssertEqual(
            TrafficFilter.resourceKind(for: make(responseHeaders: [HTTPHeader("Content-Type", "application/json")])),
            .fetch
        )
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(method: "POST")), .fetch)
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(path: "/api/users")), .fetch)
    }

    func testResourceKindClassifiesDocumentFontMediaAndWebSocket() {
        XCTAssertEqual(
            TrafficFilter.resourceKind(for: make(responseHeaders: [HTTPHeader("Content-Type", "text/html")])),
            .document
        )
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(path: "/font.woff2")), .font)
        XCTAssertEqual(TrafficFilter.resourceKind(for: make(path: "/clip.mp4")), .media)
        XCTAssertEqual(
            TrafficFilter.resourceKind(for: make(status: 101, requestHeaders: [HTTPHeader("Upgrade", "websocket")])),
            .websocket
        )
    }
}
