import XCTest
@testable import ReverseAPIProxy

final class HARExporterTests: XCTestCase {
    // MARK: - queryString

    func testQueryStringEmpty() {
        XCTAssertEqual(HARExporter.queryString(from: "/users").count, 0)
    }

    func testQueryStringSinglePair() {
        let result = HARExporter.queryString(from: "/users?id=42")
        XCTAssertEqual(result, [["name": "id", "value": "42"]])
    }

    func testQueryStringMultiplePairs() {
        let result = HARExporter.queryString(from: "/users?id=42&name=alice")
        XCTAssertEqual(result.count, 2)
        XCTAssertEqual(result[0]["name"], "id")
        XCTAssertEqual(result[1]["name"], "name")
    }

    func testQueryStringPlusDecodedAsSpace() {
        let result = HARExporter.queryString(from: "/search?q=hello+world")
        XCTAssertEqual(result, [["name": "q", "value": "hello world"]])
    }

    func testQueryStringPercentEncodedDecoded() {
        let result = HARExporter.queryString(from: "/search?q=hello%20world")
        XCTAssertEqual(result, [["name": "q", "value": "hello world"]])
    }

    func testQueryStringMixedPlusAndPercent() {
        let result = HARExporter.queryString(from: "/search?q=a+b%20c")
        XCTAssertEqual(result, [["name": "q", "value": "a b c"]])
    }

    func testQueryStringIgnoresFragment() {
        let result = HARExporter.queryString(from: "/users?id=42#section")
        XCTAssertEqual(result, [["name": "id", "value": "42"]])
    }

    func testQueryStringKeyOnly() {
        let result = HARExporter.queryString(from: "/x?debug")
        XCTAssertEqual(result, [["name": "debug", "value": ""]])
    }

    // MARK: - decodeFormComponent

    func testDecodeFormComponentPlusIsSpace() {
        XCTAssertEqual(HARExporter.decodeFormComponent("hello+world"), "hello world")
    }

    func testDecodeFormComponentPercentEncoding() {
        XCTAssertEqual(HARExporter.decodeFormComponent("caf%C3%A9"), "café")
    }

    // MARK: - entry

    func testEntryOmitsPostDataForGet() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "api.example.com", port: 443, path: "/users")
        let entry = HARExporter.entry(for: flow)
        guard let request = entry["request"] as? [String: Any] else {
            return XCTFail("missing request object")
        }
        XCTAssertNil(request["postData"], "postData must be absent for empty request body")
    }

    func testEntryIncludesPostDataForPost() {
        var flow = CapturedFlow(scheme: .https, method: "POST", host: "api.example.com", port: 443, path: "/users")
        flow.requestBody = Data("{\"name\":\"x\"}".utf8)
        flow.requestHeaders = [HTTPHeader("content-type", "application/json")]
        let entry = HARExporter.entry(for: flow)
        guard let request = entry["request"] as? [String: Any],
              let postData = request["postData"] as? [String: Any] else {
            return XCTFail()
        }
        XCTAssertEqual(postData["mimeType"] as? String, "application/json")
        XCTAssertEqual(postData["text"] as? String, "{\"name\":\"x\"}")
    }

    func testEntryBase64EncodesBinaryResponseBody() {
        var flow = CapturedFlow(scheme: .https, method: "GET", host: "h", port: 443, path: "/")
        flow.responseBody = Data([0x00, 0x01, 0xFE, 0xFF])
        let entry = HARExporter.entry(for: flow)
        guard let response = entry["response"] as? [String: Any],
              let content = response["content"] as? [String: Any] else {
            return XCTFail()
        }
        XCTAssertEqual(content["encoding"] as? String, "base64")
        XCTAssertEqual(content["text"] as? String, "AAH+/w==")
    }

    func testEntryAttachesErrorWhenPresent() {
        var flow = CapturedFlow(scheme: .https, method: "GET", host: "h", port: 443, path: "/")
        flow.error = "boom"
        let entry = HARExporter.entry(for: flow)
        XCTAssertEqual(entry["_error"] as? String, "boom")
    }

    func testEntryAbsentErrorOnSuccess() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "h", port: 443, path: "/")
        let entry = HARExporter.entry(for: flow)
        XCTAssertNil(entry["_error"])
    }

    // MARK: - full export

    func testExportProducesValidHARStructure() throws {
        var flow = CapturedFlow(scheme: .https, method: "GET", host: "api.example.com", port: 443, path: "/v1/x?q=hi")
        flow.responseStatus = 200
        flow.responseBody = Data("{}".utf8)
        flow.responseHeaders = [HTTPHeader("Content-Type", "application/json")]
        let data = try HARExporter.export([flow])
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertNotNil(json?["log"])
        if let log = json?["log"] as? [String: Any] {
            XCTAssertEqual(log["version"] as? String, "1.2")
            XCTAssertEqual((log["entries"] as? [Any])?.count, 1)
        }
    }
}
