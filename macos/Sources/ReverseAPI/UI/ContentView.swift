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
                                .frame(minWidth: 300, maxHeight: .infinity)
                            if state.selectedFlowID != nil {
                                InspectorView()
                                    .frame(minWidth: 320, idealWidth: 480, maxHeight: .infinity)
                            }
                        }
                    }
                    // Roughly half the minimum window (980pt) so the user
                    // can never compress the traffic card into the layout
                    // glitch zone we hit earlier — host/path collisions,
                    // header label overflow, inspector tabs scrolling.
                    .frame(minWidth: 540)
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

// MARK: - Action bar (mode + chips + search)

private struct ActionBar: View {
    @Environment(AppState.self) private var state
    let onOpenPalette: () -> Void

    var body: some View {
        @Bindable var bindable = state
        VStack(spacing: 0) {
            if let error = state.lastError {
                ErrorBanner(message: error)
            }
            HStack(spacing: 14) {
                ModeToggle(selection: $bindable.captureMode)
                    .disabled(state.isCapturing || state.isWorking)

                ResourceKindStrip(selectedKinds: $bindable.filter.resourceKinds)

                if activeFilterCount > 0 {
                    Button {
                        bindable.filter = TrafficFilter()
                    } label: {
                        Label("\(activeFilterCount)", systemImage: "xmark.circle.fill")
                            .labelStyle(.titleAndIcon)
                            .foregroundStyle(Theme.textSecondary)
                    }
                    .buttonStyle(.borderless)
                    .help("Clear \(activeFilterCount) active filter(s)")
                }

                CaptureStateChip()
                CATrustChip()
                SearchButton(action: onOpenPalette)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        }
        .background(Theme.appBackground)
    }

    private var activeFilterCount: Int {
        var count = 0
        if !state.filter.search.isEmpty { count += 1 }
        if state.filter.onlyErrors { count += 1 }
        count += state.filter.hosts.count
        count += state.filter.methods.count
        count += state.filter.statusBuckets.count
        count += state.filter.resourceKinds.count
        return count
    }
}

private struct ModeToggle: View {
    @Binding var selection: AppState.CaptureMode

    var body: some View {
        NSSegmented(
            labels: AppState.CaptureMode.allCases.map { $0.rawValue },
            selection: Binding(
                get: { AppState.CaptureMode.allCases.firstIndex(of: selection) ?? 0 },
                set: { selection = AppState.CaptureMode.allCases[$0] }
            )
        )
        .fixedSize()
        .help("Capture mode")
    }
}


private struct ResourceKindStrip: View {
    @Binding var selectedKinds: Set<TrafficFilter.ResourceKind>

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                Chip(title: "All", isSelected: selectedKinds.isEmpty) {
                    selectedKinds.removeAll()
                }
                ForEach(TrafficFilter.ResourceKind.allCases) { kind in
                    Chip(title: kind.rawValue, isSelected: selectedKinds.contains(kind)) {
                        if selectedKinds.contains(kind) {
                            selectedKinds.remove(kind)
                        } else {
                            selectedKinds.insert(kind)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct Chip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void
    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.medium))
                .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 3)
                .pillBackground(isActive: isSelected, isHovering: isHovering)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
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
