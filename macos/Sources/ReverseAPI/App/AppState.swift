import Foundation
import Observation
import ReverseAPIProxy

@MainActor
@Observable
final class AppState {
    private(set) var isCapturing = false
    private(set) var systemProxyEnabled = false
    private(set) var caTrustInstalled = false
    private(set) var lastError: String?

    var selectedFlowID: UUID?
    var filter = TrafficFilter()

    let store: FlowStore
    let engine: ProxyEngine
    let installer: CertificateTrustInstaller
    let systemProxy: SystemProxyController

    let port: Int
    let caDER: Data
    let caPEM: String
    let caPath: String

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

        self.store = store
        self.engine = engine
        self.installer = CertificateTrustInstaller()
        self.systemProxy = SystemProxyController()
        self.port = port
        self.caDER = Data(try root.derBytes())
        self.caPEM = try root.pem()
        self.caPath = caStore.certificateURL.path
        self.caTrustInstalled = installer.isInstalled(derBytes: self.caDER)
        self.systemProxyEnabled = (try? systemProxy.isEnabled()) ?? false

        store.subscribe(to: engine.bus)
    }

    func toggleCapture() async {
        if isCapturing {
            await stopCapture()
        } else {
            await startCapture()
        }
    }

    func startCapture() async {
        guard !isCapturing else { return }
        do {
            try await engine.start()
            isCapturing = true
            lastError = nil
        } catch {
            lastError = "Failed to start proxy: \(error)"
        }
    }

    func stopCapture() async {
        guard isCapturing else { return }
        do {
            try await engine.stop()
            isCapturing = false
        } catch {
            lastError = "Failed to stop proxy: \(error)"
        }
    }

    func installCATrust() async {
        do {
            let installer = self.installer
            let der = self.caDER
            try await Task.detached(priority: .userInitiated) {
                try installer.install(derBytes: der)
            }.value
            caTrustInstalled = true
        } catch {
            lastError = "Failed to install CA trust: \(error)"
        }
    }

    func uninstallCATrust() async {
        do {
            let installer = self.installer
            let der = self.caDER
            try await Task.detached(priority: .userInitiated) {
                try installer.uninstall(derBytes: der)
            }.value
            caTrustInstalled = false
        } catch {
            lastError = "Failed to uninstall CA trust: \(error)"
        }
    }

    func enableSystemProxy() async {
        do {
            let systemProxy = self.systemProxy
            let port = self.port
            try await Task.detached(priority: .userInitiated) {
                try systemProxy.enable(host: "127.0.0.1", port: port)
            }.value
            systemProxyEnabled = true
        } catch {
            lastError = "Failed to enable system proxy: \(error)"
        }
    }

    func disableSystemProxy() async {
        do {
            let systemProxy = self.systemProxy
            try await Task.detached(priority: .userInitiated) {
                try systemProxy.disable()
            }.value
            systemProxyEnabled = false
        } catch {
            lastError = "Failed to disable system proxy: \(error)"
        }
    }

    func clearFlows() {
        do {
            try store.clear()
            selectedFlowID = nil
        } catch {
            lastError = "Failed to clear flows: \(error)"
        }
    }
}
