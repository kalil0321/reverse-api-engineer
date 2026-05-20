import SwiftUI
import ReverseAPIProxy
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(AppState.self) private var state
    @State private var isPaletteVisible: Bool = false

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                ActionBar(onOpenPalette: { isPaletteVisible = true })
                HSplitView {
                    Card {
                        HSplitView {
                            TrafficListView()
                                .frame(minWidth: 320, maxHeight: .infinity)
                            if state.selectedFlowID != nil {
                                InspectorView()
                                    .frame(minWidth: 340, idealWidth: 480, maxHeight: .infinity)
                            }
                        }
                    }
                    // Conditional minWidth so the user can still compress the
                    // traffic card down when no inspector is showing, but the
                    // card auto-grows to fit table+inspector the moment a
                    // flow gets selected. Below 700pt with the inspector
                    // open, SwiftUI rendered the inner HSplitView wider
                    // than the Card frame, leaking past the rounded
                    // clipShape — borders disappeared, rows got clipped
                    // past the right edge, scroll + hit testing broke.
                    .frame(minWidth: state.selectedFlowID == nil ? 380 : 700)
                    // Right padding on the trailing edge of the traffic card
                    // gives the visible gap between cards. HSplitView itself
                    // owns a 1pt system divider; the padding pushes it off
                    // the card outline so the two cards read as separate.
                    .padding(.trailing, 6)

                    Card {
                        AgentPanel()
                    }
                    .frame(minWidth: 340, idealWidth: 380)
                    .padding(.leading, 6)
                }
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }

            // Dim layer (fades alone)
            if isPaletteVisible {
                Theme.overlay
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture { isPaletteVisible = false }
                    .transition(.opacity)
                    .zIndex(9)
            }

            // Palette panel (scales + fades)
            if isPaletteVisible {
                CommandPalette(isPresented: $isPaletteVisible)
                    .transition(
                        .scale(scale: 0.94, anchor: .center)
                            .combined(with: .opacity)
                            .combined(with: .offset(y: -8))
                    )
                    .zIndex(10)
            }
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.84), value: isPaletteVisible)
        .sheet(item: Binding(
            get: { state.viewingFile },
            set: { state.viewingFile = $0 }
        )) { ref in
            AgentFileViewer(url: ref.url, isPresented: Binding(
                get: { state.viewingFile != nil },
                set: { if !$0 { state.viewingFile = nil } }
            ))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.appBackground)
        .preferredColorScheme(.dark)
        .toolbar { toolbarContent }
        .task {
            await state.recoverStaleSystemProxyOnLaunch()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            state.restoreProxyBeforeExit()
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            ActionsMenu()
            CaptureButton()
        }
    }
}

// MARK: - Card

/// Inset card with rounded corners + subtle border. Used for the traffic
/// and agent containers so they read as discrete panels against the app
/// background rather than blending into a single wall of UI.
struct Card<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Theme.border, lineWidth: 1)
            }
    }
}

// MARK: - Thin divider

struct ThinDivider: View {
    var body: some View {
        Rectangle()
            .fill(Theme.border)
            .frame(height: 1)
    }
}

// MARK: - Capture button (icon-only, neutral)

private struct CaptureButton: View {
    @Environment(AppState.self) private var state

    var body: some View {
        Button {
            Task { await state.toggleCapture() }
        } label: {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 22, height: 22)
        }
        .buttonStyle(.borderless)
        .help(state.isCapturing ? "Stop capture" : "Start capture")
        .disabled(state.isWorking)
    }

    private var icon: String {
        if state.isWorking { return "hourglass" }
        return state.isCapturing ? "stop.circle.fill" : "record.circle"
    }

    private var tint: Color {
        if state.isCapturing { return Theme.danger }
        return Theme.textSecondary
    }
}

// MARK: - Actions menu

private struct ActionsMenu: View {
    @Environment(AppState.self) private var state

    var body: some View {
        Menu {
            Section {
                Picker("Mode", selection: Binding(
                    get: { state.captureMode },
                    set: { state.captureMode = $0 }
                )) {
                    ForEach(AppState.CaptureMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .disabled(state.isCapturing || state.isWorking)
            }

            Section {
                if state.caTrustInstalled {
                    Button("Remove CA trust") {
                        Task { await state.uninstallCATrust() }
                    }
                } else {
                    Button("Trust CA") {
                        Task { await state.installCATrust() }
                    }
                }
                if state.systemProxyEnabled {
                    Button("Stop routing this Mac") {
                        Task { await state.disableSystemProxy() }
                    }
                    .disabled(state.isCapturing && state.captureMode == .device)
                } else {
                    Button("Route this Mac through rae") {
                        Task { await state.enableSystemProxy() }
                    }
                    .disabled(state.isCapturing && state.captureMode == .device)
                }
            }

            Section {
                Button("Export HAR…") { exportHAR() }
                    .disabled(state.store.flows.isEmpty)
                Button("Clear traffic") {
                    state.clearFlows()
                }
                .disabled(state.store.flows.isEmpty)
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuStyle(.borderlessButton)
        .help("More actions")
    }

    private func exportHAR() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "har") ?? .json, .json]
        panel.nameFieldStringValue = "rae-\(Self.timestamp()).har"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let snapshot = state.store.flows
        Task {
            do {
                try await Task.detached(priority: .userInitiated) {
                    let data = try HARExporter.export(snapshot)
                    try data.write(to: url, options: .atomic)
                }.value
            } catch {
                await MainActor.run { _ = NSAlert(error: error).runModal() }
            }
        }
    }

    private static func timestamp() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }
}

// MARK: - Action bar (status + search)

private struct ActionBar: View {
    @Environment(AppState.self) private var state
    let onOpenPalette: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            if let error = state.lastError {
                ErrorBanner(message: error)
            }
            HStack(spacing: 14) {
                CaptureStateChip()
                CATrustChip()
                Spacer()
                SearchButton(action: onOpenPalette)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        }
        .background(Theme.appBackground)
    }
}

private struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.warn)
            Text(message)
                .font(.callout)
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(3)
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Theme.warn.opacity(0.12))
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.warn.opacity(0.25)).frame(height: 1)
        }
    }
}

// MARK: - Inline status chips (live in the ActionBar)

private struct CaptureStateChip: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
            Text(label)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(Theme.input, in: Capsule())
        .help("Capture state · 127.0.0.1:\(state.port)")
    }

    private var dotColor: Color {
        if state.isWorking { return .yellow }
        if state.isCapturing { return Theme.success }
        return Theme.textTertiary
    }

    private var label: String {
        if state.isWorking { return "working…" }
        if state.isCapturing { return "recording · \(state.port)" }
        return "idle · \(state.port)"
    }
}

private struct CATrustChip: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: state.caTrustInstalled ? "checkmark.seal.fill" : "seal")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(state.caTrustInstalled ? Theme.success : Theme.textTertiary)
            Text(state.caTrustInstalled ? "CA trusted" : "CA")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(Theme.input, in: Capsule())
        .help(state.caTrustInstalled
              ? "Root CA installed — HTTPS can be inspected"
              : "Root CA not trusted — HTTPS will fail")
    }
}

// MARK: - Search button (opens command palette)

private struct SearchButton: View {
    let action: () -> Void
    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(isHovering ? PillStyle.activeBackground : PillStyle.hoverBackground, in: Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help("Search captured traffic")
    }
}
