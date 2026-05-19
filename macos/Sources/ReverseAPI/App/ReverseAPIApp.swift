import AppKit
import SwiftUI

@main
struct ReverseAPIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var session = AppSession.live()
    @AppStorage("rae.sidebar.visible") private var isSidebarVisible = true

    var body: some Scene {
        Window("rae", id: "main") {
            switch session {
            case .ready(let state):
                ContentView(isSidebarVisible: $isSidebarVisible)
                    .environment(state)
                    .onAppear {
                        AppLifecycle.shared.state = state
                    }
                    .onDisappear {
                        Task { await state.shutdownForWindowClose() }
                    }
                    .frame(
                        minWidth: 1100,
                        maxWidth: .infinity,
                        minHeight: 700,
                        maxHeight: .infinity,
                        alignment: .topLeading
                    )
            case .failed(let error):
                BootFailureView(error: error)
                    .frame(minWidth: 500, minHeight: 300)
            }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandGroup(after: .toolbar) {
                Button(isSidebarVisible ? "Hide Sidebar" : "Show Sidebar") {
                    isSidebarVisible.toggle()
                }
                .keyboardShortcut("b", modifiers: .command)
            }
        }
    }
}

@MainActor
final class AppLifecycle {
    static let shared = AppLifecycle()
    weak var state: AppState?

    private init() {}

    func restoreProxyBeforeExit() {
        state?.restoreProxyBeforeExit()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    @MainActor
    func applicationWillTerminate(_ notification: Notification) {
        AppLifecycle.shared.restoreProxyBeforeExit()
    }
}

enum AppSession {
    case ready(AppState)
    case failed(Error)

    @MainActor
    static func live() -> AppSession {
        do {
            return .ready(try AppState())
        } catch {
            return .failed(error)
        }
    }
}

struct BootFailureView: View {
    let error: Error

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.red)
            Text("rae failed to start")
                .font(.title2)
                .bold()
            Text(String(describing: error))
                .font(.system(.body, design: .monospaced))
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .multilineTextAlignment(.center)
        }
        .padding(40)
    }
}
