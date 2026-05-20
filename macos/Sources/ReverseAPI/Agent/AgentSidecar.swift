import Foundation

actor AgentSidecar {
    struct LaunchSpec: Sendable {
        var executablePath: String
        var arguments: [String]
        var workdir: URL
        var pythonPath: [String]
        var origin: AgentRuntime.Origin

        public init(
            executablePath: String,
            arguments: [String],
            workdir: URL,
            pythonPath: [String] = [],
            origin: AgentRuntime.Origin = .fallback
        ) {
            self.executablePath = executablePath
            self.arguments = arguments
            self.workdir = workdir
            self.pythonPath = pythonPath
            self.origin = origin
        }

        public static func python3(workdir: URL) -> LaunchSpec {
            let runtime = AgentRuntime.resolve()
            return LaunchSpec(
                executablePath: runtime.executablePath,
                arguments: runtime.arguments,
                workdir: workdir,
                pythonPath: runtime.pythonPath,
                origin: runtime.origin
            )
        }

        public static func executable(at path: String, workdir: URL) -> LaunchSpec {
            LaunchSpec(executablePath: path, arguments: ["-m", "rae_agent.server"], workdir: workdir)
        }
    }

    enum SidecarError: Error, CustomStringConvertible {
        case alreadyRunning
        case failedToStart(String)
        case timedOut
        case processDied(Int32)
        case stderrSnapshot(String)

        var description: String {
            switch self {
            case .alreadyRunning: return "sidecar already running"
            case .failedToStart(let msg): return "failed to start: \(msg)"
            case .timedOut: return "sidecar did not announce its port in time"
            case .processDied(let code): return "sidecar exited with status \(code)"
            case .stderrSnapshot(let snapshot): return snapshot
            }
        }
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
        if !spec.pythonPath.isEmpty {
            let existing = environment["PYTHONPATH"]
            let combined = ([existing].compactMap { $0?.isEmpty == false ? $0 : nil } + spec.pythonPath)
                .joined(separator: ":")
            environment["PYTHONPATH"] = combined
        }
        process.environment = environment

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        do {
            try process.run()
        } catch {
            throw SidecarError.failedToStart("could not exec \(spec.executablePath): \(error.localizedDescription)")
        }
        self.process = process

        do {
            let bound = try await waitForBoundPort(stdout: stdout, stderr: stderr, deadline: timeout, process: process)
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

    private func waitForBoundPort(stdout: Pipe, stderr: Pipe, deadline: Duration, process: Process) async throws -> Int {
        let stdoutHandle = stdout.fileHandleForReading
        let stderrHandle = stderr.fileHandleForReading
        let buffer = AsyncStreamBuffer()
        let errBuffer = AsyncStreamBuffer()
        stdoutHandle.readabilityHandler = { handle in
            let chunk = handle.availableData
            if !chunk.isEmpty { buffer.append(chunk) }
        }
        stderrHandle.readabilityHandler = { handle in
            let chunk = handle.availableData
            if !chunk.isEmpty { errBuffer.append(chunk) }
        }
        defer {
            stdoutHandle.readabilityHandler = nil
            stderrHandle.readabilityHandler = nil
        }

        let deadlineDate = ContinuousClock.now.advanced(by: deadline)
        while ContinuousClock.now < deadlineDate {
            if let line = buffer.takeLine(prefix: "RAE_AGENT_LISTENING:") {
                let portString = line.dropFirst("RAE_AGENT_LISTENING:".count)
                guard let port = Int(portString) else {
                    throw SidecarError.failedToStart("unexpected line: \(line)")
                }
                // The sidecar can announce its port and crash one tick later
                // (e.g. an exception fires while `serve()` enters its first
                // accept loop). Give the runloop a beat, then re-check
                // liveness before returning the port — otherwise the caller
                // happily tries to connect a websocket to a dead process.
                try await Task.sleep(for: .milliseconds(20))
                if !process.isRunning {
                    let stderrDump = errBuffer.snapshot().trimmingCharacters(in: .whitespacesAndNewlines)
                    if !stderrDump.isEmpty {
                        throw SidecarError.stderrSnapshot(stderrDump)
                    }
                    throw SidecarError.processDied(process.terminationStatus)
                }
                return port
            }
            if !process.isRunning {
                let stderrDump = errBuffer.snapshot().trimmingCharacters(in: .whitespacesAndNewlines)
                if !stderrDump.isEmpty {
                    throw SidecarError.stderrSnapshot(stderrDump)
                }
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

    /// Only matches lines that are *complete*, i.e. terminated by a newline.
    /// Without this guard a fragmented stdout read can hand back a partial
    /// `RAE_AGENT_LISTENING:5` and we'd connect to port 5 instead of the
    /// real port once it finishes arriving.
    func takeLine(prefix: String) -> String? {
        lock.lock()
        defer { lock.unlock() }
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        let endsWithNewline = text.hasSuffix("\n")
        let segments = text.split(separator: "\n", omittingEmptySubsequences: false)
        for (index, substring) in segments.enumerated() {
            let line = String(substring)
            guard line.hasPrefix(prefix) else { continue }
            // The final segment may be a partial line (the reader has bytes
            // but the trailing \n hasn't arrived yet). Treat it as complete
            // only when `text` itself ends with \n.
            let isComplete = (index != segments.count - 1) || endsWithNewline
            if isComplete { return line }
        }
        return nil
    }

    func snapshot() -> String {
        lock.lock()
        defer { lock.unlock() }
        return String(data: data, encoding: .utf8) ?? ""
    }
}
