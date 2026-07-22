import XCTest
@testable import ReverseAPIProxy

final class ProxyEngineLifecycleTests: XCTestCase {
    /// Regression for the "capture works only once per launch" bug: stop() must
    /// keep the event-loop group alive so the same engine can start again.
    /// Previously stop() shut the group down, and the second start() failed with
    /// EventLoopError.shutdown (a capture toggle-off/on, or the cleanup after a
    /// failed device-mode start, would brick all future captures until relaunch).
    func testCaptureCanRestartAfterStop() async throws {
        let root = try CertificateAuthority.generateRoot()
        let engine = try ProxyEngine(root: root, port: 0)

        try await engine.start()
        XCTAssertTrue(engine.isRunning)
        try await engine.stop()
        XCTAssertFalse(engine.isRunning)

        // The critical assertion: starting again on the same engine succeeds.
        try await engine.start()
        XCTAssertTrue(engine.isRunning)

        try await engine.terminate()
        XCTAssertFalse(engine.isRunning)
    }

    /// stop() is a no-op when already stopped and must be safe to call twice
    /// (startCapture's failure path calls stop() after start() may have failed).
    func testStopIsIdempotent() async throws {
        let root = try CertificateAuthority.generateRoot()
        let engine = try ProxyEngine(root: root, port: 0)

        try await engine.start()
        try await engine.stop()
        try await engine.stop()  // must not throw
        XCTAssertFalse(engine.isRunning)

        try await engine.terminate()
    }
}
