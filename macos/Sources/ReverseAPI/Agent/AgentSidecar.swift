import Foundation

actor AgentSidecar {
    struct LaunchSpec: Sendable {
        var pythonExecutable: String
        var workdir: URL
    }

    enum SidecarError: Error {
        case alreadyRunning
        case failedToStart(String)
        case timedOut
    }

    private(set) var process: Process?
    private(set) var port: Int?

    func launch(_ spec: LaunchSpec) async throws -> Int {
        if let port { return port }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: spec.pythonExecutable)
        process.arguments = ["-m", "rae_agent.server"]
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

        let bound = try await waitForBoundPort(stdout: stdout)
        self.port = bound
        return bound
    }

    func terminate() {
        process?.terminate()
        process = nil
        port = nil
    }

    private func waitForBoundPort(stdout: Pipe) async throws -> Int {
        let handle = stdout.fileHandleForReading
        let deadline = Date().addingTimeInterval(15)
        var buffer = Data()
        while Date() < deadline {
            let data = handle.availableData
            if data.isEmpty {
                try await Task.sleep(for: .milliseconds(100))
                continue
            }
            buffer.append(data)
            if let text = String(data: buffer, encoding: .utf8),
               let line = text.split(separator: "\n").first(where: { $0.hasPrefix("RAE_AGENT_LISTENING:") }) {
                let portString = line.dropFirst("RAE_AGENT_LISTENING:".count)
                guard let port = Int(portString) else {
                    throw SidecarError.failedToStart("unexpected line: \(line)")
                }
                return port
            }
        }
        throw SidecarError.timedOut
    }
}
