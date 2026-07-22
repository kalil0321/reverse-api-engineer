import XCTest
@testable import ReverseAPIProxy

final class SystemProxyControllerTests: XCTestCase {
    func testShellQuoteEscapesSingleQuotes() {
        let controller = SystemProxyController()
        XCTAssertEqual(controller.shellQuote("plain"), "'plain'")
        XCTAssertEqual(controller.shellQuote("o'brien"), "'o'\\''brien'")
    }

    func testShellQuoteHandlesShellMetacharacters() {
        let controller = SystemProxyController()
        XCTAssertEqual(controller.shellQuote("a; rm -rf /"), "'a; rm -rf /'")
        XCTAssertEqual(controller.shellQuote("foo && bar"), "'foo && bar'")
    }

    func testParseGetWebProxyEnabled() {
        let output = """
        Enabled: Yes
        Server: 127.0.0.1
        Port: 8888
        Authenticated Proxy Enabled: 0
        """
        let result = SystemProxyController.parse(getWebProxyOutput: output)
        XCTAssertTrue(result.enabled)
        XCTAssertEqual(result.host, "127.0.0.1")
        XCTAssertEqual(result.port, 8888)
    }

    func testParseGetWebProxyDisabled() {
        let output = """
        Enabled: No
        Server:
        Port: 0
        Authenticated Proxy Enabled: 0
        """
        let result = SystemProxyController.parse(getWebProxyOutput: output)
        XCTAssertFalse(result.enabled)
        XCTAssertEqual(result.host, "")
        XCTAssertEqual(result.port, 0)
    }

    func testParseGetWebProxyHandlesExtraWhitespace() {
        let output = "  Enabled: Yes  \n   Server:    proxy.example.com  \n   Port:   3128"
        let result = SystemProxyController.parse(getWebProxyOutput: output)
        XCTAssertTrue(result.enabled)
        XCTAssertEqual(result.host, "proxy.example.com")
        XCTAssertEqual(result.port, 3128)
    }

    func testEnableRejectsHostWithShellMetacharacters() {
        let controller = SystemProxyController()
        for bad in ["127.0.0.1; rm -rf /", "$(whoami)", "a b"] {
            XCTAssertThrowsError(try controller.enable(host: bad, port: 8888)) { error in
                guard case SystemProxyError.invalidHost = error else {
                    XCTFail("expected invalidHost, got \(error)"); return
                }
            }
        }
    }

    func testEnableRejectsInvalidPort() {
        let controller = SystemProxyController()
        for bad in [0, 70000] {
            XCTAssertThrowsError(try controller.enable(host: "127.0.0.1", port: bad)) { error in
                guard case SystemProxyError.invalidPort = error else {
                    XCTFail("expected invalidPort, got \(error)"); return
                }
            }
        }
    }

    func testEnableRejectsEmptyHost() {
        let controller = SystemProxyController()
        XCTAssertThrowsError(try controller.enable(host: "", port: 8888)) { error in
            guard case SystemProxyError.invalidHost = error else {
                XCTFail("expected invalidHost, got \(error)"); return
            }
        }
    }
}
