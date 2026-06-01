import SwiftUI
import ReverseAPIProxy
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(AppState.self) private var state
    @State private var isPaletteVisible: Bool = false
    @State private var trafficWidth: CGFloat = 720
    @State private var dragStartWidth: CGFloat?

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                ActionBar(onOpenPalette: { isPaletteVisible = true })
                GeometryReader { geo in
                    let layout = SplitLayout(
                        totalWidth: geo.size.width,
                        trafficWidth: trafficWidth,
                        hasInspector: state.selectedFlowID != nil
                    )
                    HStack(spacing: 0) {
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
                        .frame(width: layout.trafficWidth)
                        DragHandle(width: SplitLayout.handleWidth) { delta in
                            // First gesture tick: snapshot the current width so
                            // we don't accumulate the same offset every frame.
                            if dragStartWidth == nil {
                                dragStartWidth = layout.trafficWidth
                            }
                            trafficWidth = (dragStartWidth ?? 0) + delta
                        } onEnded: {
                            dragStartWidth = nil
                            // Pin to the clamped value so the next gesture
                            // starts from where the user actually let go.
                            trafficWidth = layout.trafficWidth
                        }
                        Card {
                            AgentPanel()
                        }
                        .frame(width: layout.agentWidth)
                    }
                    .padding(12)
                    .onChange(of: state.selectedFlowID) { _, newID in
                        // When the inspector opens, the traffic card's
                        // effective minimum jumps from 380 → 720. Re-clamp
                        // the user's last manual width through SplitLayout
                        // so the card auto-grows instead of clipping past
                        // its rounded border.
                        let next = SplitLayout(
                            totalWidth: geo.size.width,
                            trafficWidth: trafficWidth,
                            hasInspector: newID != nil
                        )
                        if trafficWidth != next.trafficWidth {
                            withAnimation(.easeOut(duration: 0.2)) {
                                trafficWidth = next.trafficWidth
                            }
                        }
                    }
                }
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

// MARK: - Outer split between traffic + agent cards

/// Resolves the actual widths of the two cards from the current geometry,
/// the user-driven trafficWidth state, and whether the inspector is open.
/// Pulls the math out of ContentView.body so layout decisions live next to
/// the constants they depend on.
private struct SplitLayout {
    static let handleWidth: CGFloat = 12
    static let outerPadding: CGFloat = 12
    static let trafficMinNoInspector: CGFloat = 380
    static let trafficMinWithInspector: CGFloat = 720
    static let agentMin: CGFloat = 340

    let trafficWidth: CGFloat
    let agentWidth: CGFloat

    init(totalWidth: CGFloat, trafficWidth proposed: CGFloat, hasInspector: Bool) {
        let usable = max(0, totalWidth - 2 * Self.outerPadding - Self.handleWidth)
        let trafficMin = hasInspector ? Self.trafficMinWithInspector : Self.trafficMinNoInspector
        // Ceiling so the agent card never gets squashed below its own
        // minimum, even when the user drags the handle hard against the
        // right edge of the window.
        let trafficMax = max(trafficMin, usable - Self.agentMin)
        let clamped = min(max(proposed, trafficMin), trafficMax)
        self.trafficWidth = clamped
        self.agentWidth = max(Self.agentMin, usable - clamped)
    }
}

/// Transparent vertical strip between the two cards. The body itself is
/// invisible — we just need a hit-target for the drag gesture. NSCursor
/// flips to resizeLeftRight when the pointer hovers, so the affordance is
/// the cursor rather than a visible bar.
private struct DragHandle: View {
    let width: CGFloat
    let onDrag: (CGFloat) -> Void
    let onEnded: () -> Void

    var body: some View {
        Rectangle()
            .fill(Color.clear)
            .frame(width: width)
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeLeftRight.push()
                } else {
                    NSCursor.pop()
                }
            }
            .gesture(
                DragGesture()
                    .onChanged { value in onDrag(value.translation.width) }
                    .onEnded { _ in onEnded() }
            )
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
