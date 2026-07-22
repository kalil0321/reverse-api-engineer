import XCTest
@testable import ReverseAPI

final class JSONFormatterTests: XCTestCase {
    func testReturnsNilForEmptyData() {
        XCTAssertNil(JSONFormatter.prettyPrintJSON(Data(), contentType: "application/json"))
    }

    func testFormatsValidJSON() {
        let data = Data("{\"b\":1,\"a\":2}".utf8)
        let pretty = JSONFormatter.prettyPrintJSON(data, contentType: "application/json")
        XCTAssertNotNil(pretty)
        XCTAssertTrue(pretty?.contains("\"a\" : 2") == true || pretty?.contains("\"a\": 2") == true)
    }

    func testReturnsNilForNonJSONContentTypeAndNonJSONShape() {
        let data = Data("not json".utf8)
        let pretty = JSONFormatter.prettyPrintJSON(data, contentType: "text/plain")
        XCTAssertNil(pretty)
    }

    func testFallsBackToShapeDetectionWithoutContentType() {
        let data = Data("[1,2,3]".utf8)
        let pretty = JSONFormatter.prettyPrintJSON(data, contentType: nil)
        XCTAssertNotNil(pretty)
    }

    func testHandlesLeadingWhitespace() {
        let data = Data("   \n  {\"x\":1}".utf8)
        let pretty = JSONFormatter.prettyPrintJSON(data, contentType: nil)
        XCTAssertNotNil(pretty)
    }

    func testReturnsNilForInvalidJSON() {
        let data = Data("{not valid}".utf8)
        XCTAssertNil(JSONFormatter.prettyPrintJSON(data, contentType: "application/json"))
    }
}
