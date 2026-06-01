import Foundation
import Observation
import ReverseAPIProxy
import Security

/// Identifiable wrapper for the file the user is currently inspecting, used
/// with SwiftUI's `.sheet(item:)` so toggling between files re-renders.
struct AgentFileRef: Identifiable, Hashable {
    let url: URL
    var id: URL { url }
}

@MainActor
@Observable
final class AppState {
    enum CaptureMode: String, CaseIterable, Identifiable {
        case device = "Device"
        case manual = "Manual"

        var id: String { rawValue }
    }

    private(set) var isCapturing = false
    private(set) var systemProxyEnabled = false
    private(set) var caTrustInstalled = false
    private(set) var isWorking = false
    private(set) var lastError: String?

    var selectedFlowID: UUID?
    /// Flows the user has explicitly checked to share with the agent on the
    /// next send. When empty, the agent receives the filtered view instead.
    var agentSelection: Set<UUID> = []
    /// When set, ContentView shows AgentFileViewer for this path.
    var viewingFile: AgentFileRef?
    var filter = TrafficFilter()
    var captureMode: CaptureMode = .device

    func viewFile(at path: String) {
        viewingFile = AgentFileRef(url: URL(fileURLWithPath: path))
    }

    func deleteFlows(_ ids: Set<UUID>) {
        guard !ids.isEmpty else { return }
        if let selected = selectedFlowID, ids.contains(selected) {
            selectedFlowID = nil
        }
        agentSelection.subtract(ids)
        Task { await store.delete(ids: ids) }
    }

    let store: FlowStore
    let engine: ProxyEngine
    let installer: CertificateTrustInstaller
    let systemProxy: SystemProxyController
    let agent: AgentSession

    let port: Int
    let caDER: Data
    let caPEM: String
    let caPath: String

    private var proxySnapshot: [ProxyServiceSnapshot]?
    private let snapshotFileURL: URL

    init(port: Int = 8888) throws {
        let appSupport = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let caStore = try CAStore(applicationSupportURL: appSupport)
        let root = try caStore.loadOrCreate()
        let engine = try ProxyEngine(root: root, port: port)

        let databaseURL = caStore.directory.appendingPathComponent("flows.sqlite")
        let store = try FlowStore(databaseURL: databaseURL)

        // Shares `~/.reverse-api/` with the reverse-api-engineer CLI.
        // No-space path is also required: the Claude CLI hashes the
        // cwd into a folder name and encodes spaces inconsistently.
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let agentWorkdir = homeDir
            .appendingPathComponent(".reverse-api", isDirectory: true)
            .appendingPathComponent("agent-sessions", isDirectory: true)
        try FileManager.default.createDirectory(at: agentWorkdir, withIntermediateDirectories: true)

        // Persist the pre-rae proxy snapshot to disk while we hold it in
        // memory, so even an abrupt kill (force-quit, kernel panic, power
        // loss) leaves enough state on disk for the next launch to
        // restore the user's real settings instead of just disabling
        // the proxy and losing any pre-existing corporate proxy.
        self.snapshotFileURL = caStore.directory
            .appendingPathComponent("proxy-snapshot.json")

        self.store = store
        self.engine = engine
        self.installer = CertificateTrustInstaller()
        self.systemProxy = SystemProxyController()
        self.agent = AgentSession(workdir: agentWorkdir)
        self.port = port
        self.caDER = Data(try root.derBytes())
        self.caPEM = try root.pem()
        self.caPath = caStore.certificateURL.path
        self.caTrustInstalled = installer.isInstalled(derBytes: self.caDER)
        self.systemProxyEnabled = (try? systemProxy.isEnabled(host: "127.0.0.1", port: port)) ?? false

        // Eagerly recover from a stale snapshot left over from a previous
        // process that didn't shut down cleanly. We do this synchronously
        // in init so by the time the UI appears the user's network is
        // already in a sane state — Safari/Chrome are dead-in-the-water
        // as long as the system proxy points at our port and we're not
        // accepting connections.
        //
        // Only load the snapshot when the system proxy is currently
        // pointing at our port. Otherwise the file is just leftover from
        // a prior run that the user has since changed manually — loading
        // it would let us "restore" stale settings on the next exit and
        // overwrite the user's real, current proxy configuration.
        if self.systemProxyEnabled,
           let persisted = try? Self.readSnapshot(from: snapshotFileURL),
           !persisted.isEmpty {
            self.proxySnapshot = persisted
        } else {
            // File is either missing, malformed, or no longer relevant —
            // drop it so we don't accidentally pick it up later.
            Self.deleteSnapshot(at: snapshotFileURL)
        }

        store.subscribe(to: engine.bus)
    }

    nonisolated private static func readSnapshot(from url: URL) throws -> [ProxyServiceSnapshot] {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode([ProxyServiceSnapshot].self, from: data)
    }

    nonisolated private static func writeSnapshot(_ snapshot: [ProxyServiceSnapshot], to url: URL) throws {
        let data = try JSONEncoder().encode(snapshot)
        try data.write(to: url, options: .atomic)
    }

    nonisolated private static func deleteSnapshot(at url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    func toggleCapture() async {
        if isCapturing {
            await stopCapture()
        } else {
            await startCapture(mode: captureMode)
        }
    }

    func startCapture(mode: CaptureMode) async {
        guard !isCapturing, !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            if mode == .device {
                try await ensureCATrustInstalled()
            }
            try await engine.start()

            if mode == .device {
                do {
                    try await applySystemProxy()
                } catch {
                    try? await engine.stop()
                    throw error
                }
            }

            isCapturing = true
            lastError = nil
        } catch {
            isCapturing = false
            lastError = "Could not start capture: \(error)"
        }
    }

    func stopCapture() async {
        guard isCapturing, !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        var stopError: Error?
        if proxySnapshot != nil {
            do {
                try await restoreSystemProxy()
            } catch {
                stopError = error
            }
        }

        do {
            try await engine.stop()
            isCapturing = false
        } catch {
            stopError = error
        }

        if let stopError {
            if proxySnapshot != nil {
                systemProxyEnabled = (try? systemProxy.isEnabled(host: "127.0.0.1", port: port)) ?? false
            }
            lastError = "Could not stop capture cleanly: \(stopError)"
        } else {
            lastError = nil
        }
    }

    private func ensureCATrustInstalled() async throws {
        if installer.isInstalled(derBytes: caDER) {
            caTrustInstalled = true
            return
        }

        let installer = self.installer
        let der = self.caDER
        try await Task.detached(priority: .userInitiated) {
            try installer.install(derBytes: der)
        }.value
        caTrustInstalled = installer.isInstalled(derBytes: caDER)
        if !caTrustInstalled {
            throw CertificateTrustError.trustFailed(errSecAuthFailed)
        }
    }

    func installCATrust() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            try await ensureCATrustInstalled()
            lastError = nil
        } catch {
            lastError = "Failed to install CA trust: \(error)"
        }
    }

    func uninstallCATrust() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            let installer = self.installer
            let der = self.caDER
            try await Task.detached(priority: .userInitiated) {
                try installer.uninstall(derBytes: der)
            }.value
            caTrustInstalled = false
            lastError = nil
        } catch {
            lastError = "Failed to uninstall CA trust: \(error)"
        }
    }

    func enableSystemProxy() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            try await applySystemProxy()
            lastError = nil
        } catch {
            lastError = "Failed to enable system proxy: \(error)"
        }
    }

    func disableSystemProxy() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            try await restoreSystemProxy()
            lastError = nil
        } catch {
            lastError = "Failed to disable system proxy: \(error)"
        }
    }

    func clearFlows() {
        guard !isWorking else { return }
        isWorking = true
        Task {
            defer { isWorking = false }
            do {
                try await store.clear()
                selectedFlowID = nil
                // Stale UUIDs in agentSelection would leave the agent
                // panel in "N selected" mode with nothing to actually
                // send — wipe alongside the flows.
                agentSelection.removeAll()
                lastError = nil
            } catch {
                lastError = "Failed to clear flows: \(error)"
            }
        }
    }

    func recoverStaleSystemProxyOnLaunch() async {
        guard systemProxyEnabled, !isCapturing, !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            if let snapshot = proxySnapshot, !snapshot.isEmpty {
                // Best-case: previous run got far enough to persist the
                // user's pre-rae proxy state. Restore it verbatim so any
                // corporate proxy / VPN config the user had is preserved.
                try await restoreSystemProxy()
                lastError = "Restored previous proxy settings from a stale session."
            } else {
                // No snapshot on disk but the system proxy is still pointing
                // at 127.0.0.1:<our port>. Best we can do is turn it off so
                // browsers can reach the internet again.
                try await disableCurrentRaeProxy()
                lastError = "Recovered stale device proxy from a previous session."
            }
        } catch {
            lastError = "Device proxy points at rae, but could not be repaired automatically: \(error)"
        }
    }

    func restoreProxyBeforeExit() {
        if let snapshot = proxySnapshot {
            try? systemProxy.restore(snapshot)
            proxySnapshot = nil
            systemProxyEnabled = false
        } else if systemProxyEnabled {
            try? systemProxy.disable(host: "127.0.0.1", port: port)
            systemProxyEnabled = false
        }
        // Either way the on-disk sentinel is no longer accurate — drop it
        // so the next launch doesn't try to restore stale data.
        Self.deleteSnapshot(at: snapshotFileURL)
    }

    func shutdownForWindowClose() async {
        restoreProxyBeforeExit()
        if isCapturing {
            do {
                try await engine.stop()
                isCapturing = false
            } catch {
                lastError = "Could not stop capture cleanly: \(error)"
            }
        }
        isWorking = false
    }

    func terminate() async {
        restoreProxyBeforeExit()
        do {
            try await engine.terminate()
            isCapturing = false
            isWorking = false
        } catch {
            lastError = "Could not terminate proxy cleanly: \(error)"
        }
    }

    private func applySystemProxy() async throws {
        let systemProxy = self.systemProxy
        let port = self.port
        let snapshotURL = self.snapshotFileURL
        let snapshot = try await Task.detached(priority: .userInitiated) {
            let snapshot = try systemProxy.snapshot()
            // Write the snapshot to disk BEFORE flipping the system proxy.
            // If this fails (read-only volume, sandbox refusal, disk full)
            // we must NOT flip the proxy — otherwise a subsequent crash
            // would leave the user with no way to recover their original
            // settings.
            try Self.writeSnapshot(snapshot, to: snapshotURL)
            do {
                try systemProxy.enable(host: "127.0.0.1", port: port)
                return snapshot
            } catch {
                try? systemProxy.restore(snapshot)
                Self.deleteSnapshot(at: snapshotURL)
                throw error
            }
        }.value
        proxySnapshot = snapshot
        systemProxyEnabled = true
    }

    private func restoreSystemProxy() async throws {
        let systemProxy = self.systemProxy
        let port = self.port
        let snapshot = proxySnapshot
        let snapshotURL = self.snapshotFileURL
        try await Task.detached(priority: .userInitiated) {
            if let snapshot {
                try systemProxy.restore(snapshot)
            } else {
                try systemProxy.disable(host: "127.0.0.1", port: port)
            }
            Self.deleteSnapshot(at: snapshotURL)
        }.value
        proxySnapshot = nil
        systemProxyEnabled = false
    }

    private func disableCurrentRaeProxy() async throws {
        let systemProxy = self.systemProxy
        let port = self.port
        let snapshotURL = self.snapshotFileURL
        try await Task.detached(priority: .userInitiated) {
            try systemProxy.disable(host: "127.0.0.1", port: port)
            Self.deleteSnapshot(at: snapshotURL)
        }.value
        proxySnapshot = nil
        systemProxyEnabled = false
    }
}
