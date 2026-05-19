import Foundation
import Observation
import ReverseAPIProxy

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
    var filter = TrafficFilter()
    var captureMode: CaptureMode = .device

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

        let agentWorkdir = caStore.directory.appendingPathComponent("agent-sessions", isDirectory: true)
        try FileManager.default.createDirectory(at: agentWorkdir, withIntermediateDirectories: true)

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

        store.subscribe(to: engine.bus)
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

    func installCATrust() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            let installer = self.installer
            let der = self.caDER
            try await Task.detached(priority: .userInitiated) {
                try installer.install(derBytes: der)
            }.value
            caTrustInstalled = true
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
                lastError = nil
            } catch {
                lastError = "Failed to clear flows: \(error)"
            }
        }
    }

    func recoverStaleSystemProxyOnLaunch() async {
        guard systemProxyEnabled, !isCapturing, proxySnapshot == nil, !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            try await disableCurrentRaeProxy()
            lastError = "Recovered stale device proxy from a previous session."
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
        let snapshot = try await Task.detached(priority: .userInitiated) {
            let snapshot = try systemProxy.snapshot()
            do {
                try systemProxy.enable(host: "127.0.0.1", port: port)
                return snapshot
            } catch {
                try? systemProxy.restore(snapshot)
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
        try await Task.detached(priority: .userInitiated) {
            if let snapshot {
                try systemProxy.restore(snapshot)
            } else {
                try systemProxy.disable(host: "127.0.0.1", port: port)
            }
        }.value
        proxySnapshot = nil
        systemProxyEnabled = false
    }

    private func disableCurrentRaeProxy() async throws {
        let systemProxy = self.systemProxy
        let port = self.port
        try await Task.detached(priority: .userInitiated) {
            try systemProxy.disable(host: "127.0.0.1", port: port)
        }.value
        proxySnapshot = nil
        systemProxyEnabled = false
    }
}
