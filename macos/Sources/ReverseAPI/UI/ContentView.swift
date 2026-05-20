import SwiftUI
import ReverseAPIProxy
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(AppState.self) private var state
    @Binding var isAgentVisible: Bool
    @State private var isPaletteVisible: Bool = false

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                ActionBar(onOpenPalette: { isPaletteVisible = true })
                ThinDivider()
                HStack(spacing: 0) {
                    HSplitView {
                        TrafficListView()
                            .frame(minWidth: 420, maxHeight: .infinity)

                        if state.selectedFlowID != nil {
                            InspectorView()
                                .frame(minWidth: 360, idealWidth: 520, maxHeight: .infinity)
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                    AgentPanel()
                        .frame(width: 380)
                        .offset(x: isAgentVisible ? 0 : 380)
                        .frame(width: isAgentVisible ? 380 : 0)
                        .clipped()
                        .allowsHitTesting(isAgentVisible)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                ThinDivider()
                StatusBar()
            }

            // Hidden button to capture ⌘K globally
            Button("Search") {
                isPaletteVisible.toggle()
            }
            .keyboardShortcut("k", modifiers: [.command])
            .opacity(0)
            .frame(width: 0, height: 0)

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
        .animation(.spring(response: 0.42, dampingFraction: 0.86), value: isAgentVisible)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.appBackground)
        .preferredColorScheme(.dark)
        .toolbar { toolbarContent }
        .task {
            await state.recoverStaleSystemProxyOnLaunch()
        }
        .onReceive(NotificationCenter.default.publisher(for: .toggleRaeAgent)) { _ in
            isAgentVisible.toggle()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            state.restoreProxyBeforeExit()
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                isAgentVisible.toggle()
            } label: {
                Image(systemName: isAgentVisible ? "sparkles.rectangle.stack.fill" : "sparkles.rectangle.stack")
            }
            .help(isAgentVisible ? "Hide agent" : "Show agent")
            .keyboardShortcut("j", modifiers: [.command])

            ActionsMenu()

            CaptureButton()
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
        .help(state.isCapturing ? "Stop capture (⌘R)" : "Start capture (⌘R)")
        .disabled(state.isWorking)
        .keyboardShortcut("r", modifiers: [.command])
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
                    .keyboardShortcut("e", modifiers: [.command, .shift])
                    .disabled(state.store.flows.isEmpty)
                Button("Clear traffic") {
                    state.clearFlows()
                }
                .keyboardShortcut("k", modifiers: [.command])
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

                SearchButton(action: onOpenPalette)

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

// MARK: - Status bar (footer)

private struct StatusBar: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 12) {
            StatusDot(color: state.isCapturing ? Theme.success : Theme.textTertiary)
            Text(captureLabel)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)

            Dot()

            Image(systemName: state.caTrustInstalled ? "checkmark.seal.fill" : "seal")
                .foregroundStyle(state.caTrustInstalled ? Theme.success : Theme.textTertiary)
                .font(.caption)
            Text(state.caTrustInstalled ? "CA trusted" : "CA not trusted")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)

            Spacer()

            Text("\(state.store.flows.count) flows")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .monospacedDigit()
                .contentTransition(.numericText())
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(Theme.surface)
    }

    private var captureLabel: String {
        if state.isWorking { return "working…" }
        if state.isCapturing { return "recording · 127.0.0.1:\(state.port)" }
        return "idle · 127.0.0.1:\(state.port)"
    }
}

private struct StatusDot: View {
    let color: Color
    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 7, height: 7)
    }
}

private struct Dot: View {
    var body: some View {
        Circle()
            .fill(Theme.textTertiary.opacity(0.5))
            .frame(width: 3, height: 3)
    }
}

// MARK: - Search button (opens command palette)

private struct SearchButton: View {
    let action: () -> Void
    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                Text("⌘K")
                    .font(.system(.caption2, design: .monospaced).weight(.semibold))
                    .foregroundStyle(Theme.textTertiary)
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 5)
            .background(isHovering ? PillStyle.activeBackground : PillStyle.hoverBackground, in: Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help("Search captured traffic (⌘K)")
    }
}
