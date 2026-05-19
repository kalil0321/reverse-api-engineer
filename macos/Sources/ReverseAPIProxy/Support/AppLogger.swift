import Foundation
import os

public struct AppLogger: Sendable {
    private let logger: Logger

    public init(_ category: String) {
        self.logger = Logger(subsystem: "app.reverseapi", category: category)
    }

    public func debug(_ message: @autoclosure () -> String) {
        logger.debug("\(message(), privacy: .public)")
    }

    public func info(_ message: @autoclosure () -> String) {
        logger.info("\(message(), privacy: .public)")
    }

    public func warn(_ message: @autoclosure () -> String) {
        logger.warning("\(message(), privacy: .public)")
    }

    public func error(_ message: @autoclosure () -> String) {
        logger.error("\(message(), privacy: .public)")
    }
}
