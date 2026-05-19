import XCTest
import NIOHTTP1
@testable import ReverseAPIProxy

final class WebSocketDetectionTests: XCTestCase {
    func testDetectsLowercaseWebsocket() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "websocket")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/ws", headers: headers)
        XCTAssertTrue(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testDetectsCapitalizedWebSocket() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "WebSocket")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/ws", headers: headers)
        XCTAssertTrue(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testDetectsCommaSeparatedValues() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "h2c, websocket")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/ws", headers: headers)
        XCTAssertTrue(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testDetectsWebsocketAsSecondToken() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "h2c,websocket")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/ws", headers: headers)
        XCTAssertTrue(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testDoesNotDetectWhenAbsent() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "h2c")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/ws", headers: headers)
        XCTAssertFalse(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testDoesNotDetectWhenHeaderMissing() {
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/", headers: HTTPHeaders())
        XCTAssertFalse(ProxyHandler.isWebSocketUpgrade(head))
    }

    func testMultipleUpgradeHeaderLinesScanned() {
        var headers = HTTPHeaders()
        headers.add(name: "Upgrade", value: "h2c")
        headers.add(name: "Upgrade", value: "websocket")
        let head = HTTPRequestHead(version: .http1_1, method: .GET, uri: "/", headers: headers)
        XCTAssertTrue(ProxyHandler.isWebSocketUpgrade(head))
    }
}
