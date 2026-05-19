import XCTest
import ReverseAPIProxy
@testable import ReverseAPI

final class AgentFlowPayloadTests: XCTestCase {
    func testEncodedBodyEmptyIsNil() {
        XCTAssertNil(AgentFlowPayload.encodedBody(Data(), limit: 1000))
    }

    func testEncodedBodyReturnsUTF8WhenShortEnough() {
        let data = Data("hello".utf8)
        XCTAssertEqual(AgentFlowPayload.encodedBody(data, limit: 1000), "hello")
    }

    func testEncodedBodyTruncatesLongerInput() {
        let data = Data(repeating: 0x41, count: 1000)
        let result = AgentFlowPayload.encodedBody(data, limit: 100)
        XCTAssertNotNil(result)
        XCTAssertTrue(result?.contains("…<truncated 900 bytes>") == true)
    }

    func testEncodedBodyHandlesBinaryUnderLimit() {
        let data = Data([0xFF, 0xFE, 0xFD])
        let result = AgentFlowPayload.encodedBody(data, limit: 1000)
        XCTAssertEqual(result, "<binary:3 bytes>")
    }

    func testEncodedBodyHandlesBinaryOverLimit() {
        let data = Data(repeating: 0xFF, count: 2000)
        let result = AgentFlowPayload.encodedBody(data, limit: 100)
        XCTAssertEqual(result, "<binary:2000 bytes, truncated>")
    }

    func testInitFromFlowProducesExpectedFields() {
        var flow = CapturedFlow(scheme: .https, method: "GET", host: "api.x", port: 443, path: "/v1")
        flow.responseStatus = 200
        flow.requestHeaders = [HTTPHeader("X", "1")]
        let payload = AgentFlowPayload(flow)
        XCTAssertEqual(payload.method, "GET")
        XCTAssertEqual(payload.scheme, "https")
        XCTAssertEqual(payload.responseStatus, 200)
        XCTAssertEqual(payload.requestHeaders, [["X", "1"]])
    }
}

final class AgentEventDecoderTests: XCTestCase {
    func testDecodeAssistantText() throws {
        let data = Data("""
        {"type":"assistant_text","id":"abc","text":"hello"}
        """.utf8)
        let event = try AgentEventDecoder.decode(data)
        guard case .assistantText(let chatID, _, let text) = event else {
            return XCTFail("wrong event")
        }
        XCTAssertEqual(chatID, "abc")
        XCTAssertEqual(text, "hello")
    }

    func testDecodeToolUse() throws {
        let data = Data("""
        {"type":"tool_use","id":"abc","name":"Write","input":{"file_path":"x.py"}}
        """.utf8)
        let event = try AgentEventDecoder.decode(data)
        guard case .toolUse(_, _, let name, let json) = event else { return XCTFail() }
        XCTAssertEqual(name, "Write")
        XCTAssertTrue(json.contains("file_path"))
    }

    func testDecodeFileWritten() throws {
        let data = Data("""
        {"type":"file_written","id":"abc","path":"/tmp/x.py"}
        """.utf8)
        let event = try AgentEventDecoder.decode(data)
        guard case .fileWritten(_, _, let path) = event else { return XCTFail() }
        XCTAssertEqual(path, "/tmp/x.py")
    }

    func testDecodeError() throws {
        let data = Data("""
        {"type":"error","message":"boom"}
        """.utf8)
        let event = try AgentEventDecoder.decode(data)
        guard case .error(let chatID, _, let message) = event else { return XCTFail() }
        XCTAssertNil(chatID)
        XCTAssertEqual(message, "boom")
    }

    func testDecodeComplete() throws {
        let data = Data("""
        {"type":"complete","id":"abc","workdir":"/tmp/out","files":["a.py","b.py"]}
        """.utf8)
        let event = try AgentEventDecoder.decode(data)
        guard case .complete(_, _, let workdir, let files) = event else { return XCTFail() }
        XCTAssertEqual(workdir, "/tmp/out")
        XCTAssertEqual(files, ["a.py", "b.py"])
    }

    func testDecodeRejectsUnknownType() {
        let data = Data("""
        {"type":"mystery"}
        """.utf8)
        XCTAssertThrowsError(try AgentEventDecoder.decode(data))
    }

    func testDecodeRejectsInvalidJSON() {
        let data = Data("not json".utf8)
        XCTAssertThrowsError(try AgentEventDecoder.decode(data))
    }
}
