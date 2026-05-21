import AppKit
import SwiftUI

@main
struct ReverseAPIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var session = AppSession.live()
    /// Splash gate — visible for ~1.6s on launch so the wordmark gets a
    /// brand moment instead of the window flashing through an empty
    /// frame. Flips to false after the timer fires.
    @State private var isShowingSplash = true

    init() {
        // Register the bundled Fraunces font *here*, not in
        // applicationDidFinishLaunching — `App.init()` runs before any
        // View body is computed, while the delegate's launch callback
        // fires after the run loop starts. Doing it late means the
        // SplashView's first paint resolves `Font.fraunces(...)` to a
        // fallback (SF Italic) and only flips to Fraunces on a later
        // layout pass, which reads as the wordmark "morphing" mid-anim.
        BrandFont.bootstrap()
    }

    var body: some Scene {
        Window("rae", id: "main") {
            ZStack {
                mainContent
                    .opacity(isShowingSplash ? 0 : 1)
                if isShowingSplash {
                    SplashView()
                        .transition(.opacity)
                }
            }
            .task {
                try? await Task.sleep(for: .milliseconds(1600))
                withAnimation(.easeOut(duration: 0.45)) {
                    isShowingSplash = false
                }
            }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }

    @ViewBuilder
    private var mainContent: some View {
        switch session {
        case .ready(let state):
            ContentView()
                .environment(state)
                .onAppear {
                    AppLifecycle.shared.state = state
                }
                .onDisappear {
                    Task { await state.shutdownForWindowClose() }
                }
                .background(WindowAccessor { window in
                    window.title = ""
                    window.titleVisibility = .hidden
                    window.titlebarAppearsTransparent = true
                    window.isOpaque = true
                    // Dynamic NSColor under the hood — flips automatically
                    // when the system appearance changes.
                    window.backgroundColor = NSColor(Theme.appBackground)
                })
                .frame(
                    // Bumped so the traffic card can always fit
                    // table+inspector side by side (its inner HSplitView
                    // needs ~700pt) without compressing past its
                    // rounded border into a glitchy state. Old 980pt
                    // window minimum was below that threshold.
                    minWidth: 1100,
                    maxWidth: .infinity,
                    minHeight: 640,
                    maxHeight: .infinity,
                    alignment: .topLeading
                )
        case .failed(let error):
            BootFailureView(error: error)
                .frame(minWidth: 500, minHeight: 300)
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
    private var isTerminating = false
    private var signalSources: [DispatchSourceSignal] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Font bootstrap happens in `ReverseAPIApp.init()` so it lands
        // before any view body is computed — see the comment there.

        // `swift run` launches a bare SwiftPM executable with no .app bundle
        // and no Info.plist, so macOS doesn't treat it as a regular GUI app —
        // the window never reliably becomes key and AppKit text fields can't
        // become first responder, which is why typing into the search palette
        // and agent composer silently fails. Explicitly switching to .regular
        // activation policy and activating in front of other apps gives the
        // process a proper foreground app status. No-op when the binary is
        // launched from a real .app bundle.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        // No longer force `.darkAqua` — the Theme tokens are dynamic NSColors
        // and ContentView no longer pins `.preferredColorScheme(.dark)`,
        // so light/dark now follows the system setting.
        installSignalHandlers()
    }

    /// Restore the system proxy before exiting on SIGINT / SIGTERM / SIGHUP.
    /// Activity Monitor's "Quit" / "Force Quit", `kill <pid>`, terminal Ctrl-C
    /// from `swift run` and shutdown all hit this path. AppKit's normal
    /// applicationShouldTerminate doesn't fire for these, so without this
    /// the system proxy stays pointing at 127.0.0.1:<port> with nothing
    /// listening — exactly the "Safari can't connect" symptom users see.
    private func installSignalHandlers() {
        for sig in [SIGINT, SIGTERM, SIGHUP] {
            // Ignore the default signal action FIRST so the dispatch source
            // gets a chance to run before the process gets killed by the
            // kernel's default handler.
            signal(sig, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
            source.setEventHandler { [weak self] in
                guard let self else { exit(0) }
                // Queue is .main — we're already on the main actor, just
                // assert it so we can call @MainActor methods without
                // hopping through an async Task.
                MainActor.assumeIsolated { self.handleSignal(sig) }
            }
            source.resume()
            signalSources.append(source)
        }
    }

    @MainActor
    private func handleSignal(_ sig: Int32) {
        guard !isTerminating else { return }
        isTerminating = true
        // Synchronous restore — we have no async budget once the OS has
        // decided to kill us. The proxy state is the priority; the engine
        // + agent sidecar would normally clean up too but they'd race the
        // process exit anyway.
        AppLifecycle.shared.restoreProxyBeforeExit()
        // Re-raise the signal with the default handler so the process
        // actually exits with the right termination status.
        signal(sig, SIG_DFL)
        raise(sig)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    @MainActor
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !isTerminating else { return .terminateNow }
        guard let state = AppLifecycle.shared.state else { return .terminateNow }

        isTerminating = true
        Task {
            await state.terminate()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    @MainActor
    func applicationWillTerminate(_ notification: Notification) {
        if !isTerminating {
            AppLifecycle.shared.restoreProxyBeforeExit()
        }
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

/// Grabs the hosting NSWindow once it's attached so we can tweak title visibility,
/// titlebar transparency, and the window background — none of which SwiftUI's
/// Scene API exposes. Uses `viewDidMoveToWindow` so the window is guaranteed
/// to exist when `configure` runs (unlike DispatchQueue.main.async hacks).
private struct WindowAccessor: NSViewRepresentable {
    let configure: (NSWindow) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = WindowReadingView()
        view.onWindow = configure
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        if let view = nsView as? WindowReadingView {
            view.onWindow = configure
        }
    }

    final class WindowReadingView: NSView {
        var onWindow: ((NSWindow) -> Void)?
        private var configured = false

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard let window, !configured else { return }
            configured = true
            // Defer to next runloop tick — running AppKit window mutations during
            // the SwiftUI hosting view's first layout can throw inside Core
            // Animation's commit phase on macOS 14+.
            DispatchQueue.main.async { [weak self] in
                self?.onWindow?(window)
            }
        }

        // Never intercept mouse / keyboard events: this view exists solely to
        // bridge SwiftUI to its hosting NSWindow, not to participate in the
        // responder or hit-testing chain. Returning nil lets clicks fall
        // through to the SwiftUI content below.
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override var acceptsFirstResponder: Bool { false }
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
