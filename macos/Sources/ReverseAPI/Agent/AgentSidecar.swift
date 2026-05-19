import Foundation

actor AgentSidecar {
    struct LaunchSpec: Sendable {
        var executablePath: String
        var arguments: [String]
        var workdir: URL

        public init(executablePath: String, arguments: [String], workdir: URL) {
            self.executablePath = executablePath
            self.arguments = arguments
            self.workdir = workdir
        }

        public static func python3(workdir: URL) -> LaunchSpec {
            LaunchSpec(
                executablePath: "/usr/bin/env",
                arguments: ["python3", "-m", "rae_agent.server"],
                workdir: workdir
            )
        }

        public static func executable(at path: String, workdir: URL) -> LaunchSpec {
            LaunchSpec(executablePath: path, arguments: ["-m", "rae_agent.server"], workdir: workdir)
        }
    }

    enum SidecarError: Error {
        case alreadyRunning
        case failedToStart(String)
        case timedOut
        case processDied(Int32)
    }

    private(set) var process: Process?
    private(set) var port: Int?

    func launch(_ spec: LaunchSpec, timeout: Duration = .seconds(15)) async throws -> Int {
        if let port, let process, process.isRunning { return port }
        if port != nil || process != nil {
            terminate()
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: spec.executablePath)
        process.arguments = spec.arguments
        var environment = ProcessInfo.processInfo.environment
        environment["RAE_AGENT_HOST"] = "127.0.0.1"
        environment["RAE_AGENT_PORT"] = "0"
        environment["RAE_AGENT_WORKDIR"] = spec.workdir.path
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        self.process = process

        do {
            let bound = try await waitForBoundPort(stdout: stdout, deadline: timeout, process: process)
            self.port = bound
            return bound
        } catch {
            if process.isRunning {
                process.terminate()
            }
            self.process = nil
            self.port = nil
            throw error
        }
    }

    func terminate() {
        guard let process else { return }
        if process.isRunning {
            process.terminate()
        }
        self.process = nil
        self.port = nil
    }

    private func waitForBoundPort(stdout: Pipe, deadline: Duration, process: Process) async throws -> Int {
        let handle = stdout.fileHandleForReading
        let buffer = AsyncStreamBuffer()
        handle.readabilityHandler = { fileHandle in
            let chunk = fileHandle.availableData
            if !chunk.isEmpty {
                buffer.append(chunk)
            }
        }
        defer { handle.readabilityHandler = nil }

        let deadlineDate = ContinuousClock.now.advanced(by: deadline)
        while ContinuousClock.now < deadlineDate {
            if let line = buffer.takeLine(prefix: "RAE_AGENT_LISTENING:") {
                let portString = line.dropFirst("RAE_AGENT_LISTENING:".count)
                guard let port = Int(portString) else {
                    throw SidecarError.failedToStart("unexpected line: \(line)")
                }
                return port
            }
            if !process.isRunning {
                throw SidecarError.processDied(process.terminationStatus)
            }
            try await Task.sleep(for: .milliseconds(50))
        }
        throw SidecarError.timedOut
    }
}

private final class AsyncStreamBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()

    func append(_ chunk: Data) {
        lock.lock()
        defer { lock.unlock() }
        data.append(chunk)
    }

    func takeLine(prefix: String) -> String? {
        lock.lock()
        defer { lock.unlock() }
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        for line in text.split(separator: "\n") {
            if line.hasPrefix(prefix) { return String(line) }
        }
        return nil
    }
}
