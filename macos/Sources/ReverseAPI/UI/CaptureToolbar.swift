import SwiftUI
import AppKit
import ReverseAPIProxy
import UniformTypeIdentifiers

struct CaptureToolbar: View {
    @Environment(AppState.self) private var state
    @Binding var isSidebarVisible: Bool

    var body: some View {
        @Bindable var bindable = state

        return VStack(alignment: .leading, spacing: 20) {
            brandHeader

            VStack(alignment: .leading, spacing: 10) {
                SidebarSectionLabel("Capture")
                captureButton
                CaptureModePicker(selection: $bindable.captureMode)
                    .disabled(state.isCapturing || state.isWorking)
            }

            VStack(alignment: .leading, spacing: 8) {
                SidebarSectionLabel("Readiness")
                SidebarStatusRow(
                    title: state.isCapturing ? "Proxy running" : "Proxy stopped",
                    detail: "127.0.0.1:\(state.port)",
                    systemImage: "record.circle",
                    tint: state.isCapturing ? .green : .secondary
                )
                SidebarStatusRow(
                    title: state.systemProxyEnabled ? "Device routed" : "Device not routed",
                    detail: state.captureMode == .device ? "This Mac is automatic" : "Manual clients only",
                    systemImage: "network",
                    tint: state.systemProxyEnabled ? .green : .orange
                )
                SidebarStatusRow(
                    title: state.caTrustInstalled ? "CA trusted" : "CA not trusted",
                    detail: state.caTrustInstalled ? "HTTPS ready" : "HTTPS may fail",
                    systemImage: "seal",
                    tint: state.caTrustInstalled ? .green : .orange
                )
            }

            VStack(alignment: .leading, spacing: 8) {
                SidebarSectionLabel("Actions")
                trustButton
                systemProxyButton
                exportButton
                clearButton
            }

            if let error = state.lastError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(4)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.red.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            }

            Spacer()

            VStack(alignment: .leading, spacing: 6) {
                Text("\(state.store.flows.count)")
                    .font(.system(.title, design: .rounded).weight(.semibold))
                    .contentTransition(.numericText())
                Text("captured flows")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
        }
        .padding(18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .controlBackgroundColor),
                    Color(nsColor: .underPageBackgroundColor).opacity(0.82),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }

    private var brandHeader: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.accentColor.opacity(0.16))
                Image(systemName: "waveform.path.ecg")
                    .foregroundStyle(Color.accentColor)
                    .font(.system(size: 17, weight: .semibold))
            }
            .frame(width: 36, height: 36)

            VStack(alignment: .leading, spacing: 1) {
                Text("rae")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                Text(statusLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            Button {
                isSidebarVisible = false
            } label: {
                Image(systemName: "sidebar.left")
                    .font(.system(size: 15, weight: .medium))
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Hide sidebar")
        }
    }

    private func exportHAR() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "har") ?? .json, .json]
        panel.nameFieldStringValue = "rae-\(Self.exportTimestamp()).har"
        panel.canCreateDirectories = true
        let response = panel.runModal()
        guard response == .OK, let url = panel.url else { return }
        let flows = state.store.flows
        Task {
            do {
                try await Task.detached(priority: .userInitiated) {
                    let data = try HARExporter.export(flows)
                    try data.write(to: url, options: .atomic)
                }.value
            } catch {
                NSAlert(error: error).runModal()
            }
        }
    }

    private static func exportTimestamp() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: Date())
    }

    private var captureButton: some View {
        Button {
            Task { await state.toggleCapture() }
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(captureButtonForeground.opacity(0.16))
                    Image(systemName: captureIcon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(captureButtonForeground)
                }
                .frame(width: 42, height: 42)

                VStack(alignment: .leading, spacing: 2) {
                    Text(captureTitle)
                        .font(.headline.weight(.semibold))
                    Text(captureSubtitle)
                        .font(.caption)
                        .foregroundStyle(captureButtonForeground.opacity(0.78))
                        .lineLimit(2)
                }

                Spacer()

                Image(systemName: state.isCapturing ? "stop.fill" : "arrow.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(captureButtonForeground.opacity(0.85))
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 82)
            .background(captureButtonBackground, in: RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(captureButtonForeground.opacity(0.26), lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
        .disabled(state.isWorking)
        .help(state.captureMode == .device
              ? "Start proxy capture and route macOS HTTP/HTTPS traffic through it"
              : "Start proxy capture without changing macOS network settings")
    }

    private var trustButton: some View {
        Button {
            Task {
                if state.caTrustInstalled {
                    await state.uninstallCATrust()
                } else {
                    await state.installCATrust()
                }
            }
        } label: {
            SidebarActionLabel(
                title: state.caTrustInstalled ? "Remove CA trust" : "Trust CA",
                systemImage: state.caTrustInstalled ? "checkmark.seal.fill" : "seal"
            )
        }
        .buttonStyle(.plain)
        .disabled(state.isWorking)
        .help(state.caTrustInstalled
              ? "Remove the rae root certificate from the current user's trust store"
              : "Trust the rae root certificate so HTTPS requests can be inspected")
    }

    private var systemProxyButton: some View {
        Button {
            Task {
                if state.systemProxyEnabled {
                    await state.disableSystemProxy()
                } else {
                    await state.enableSystemProxy()
                }
            }
        } label: {
            SidebarActionLabel(
                title: state.systemProxyEnabled ? "Unroute device" : "Route device",
                systemImage: state.systemProxyEnabled ? "network.badge.shield.half.filled" : "network"
            )
        }
        .buttonStyle(.plain)
        .disabled(state.isWorking || (state.isCapturing && state.captureMode == .device))
        .help("Toggle macOS HTTP/HTTPS proxy for active network services")
    }

    private var exportButton: some View {
        Button {
            exportHAR()
        } label: {
            SidebarActionLabel(title: "Export HAR", systemImage: "square.and.arrow.up")
        }
        .buttonStyle(.plain)
        .disabled(state.store.flows.isEmpty || state.isWorking)
        .help("Export all captured flows to a .har file")
    }

    private var clearButton: some View {
        Button {
            state.clearFlows()
        } label: {
            SidebarActionLabel(title: "Clear traffic", systemImage: "trash")
        }
        .buttonStyle(.plain)
        .disabled(state.store.flows.isEmpty || state.isWorking)
        .help("Remove captured flows from the list and local database")
    }

    private var captureTitle: String {
        if state.isWorking { return "Working" }
        if state.isCapturing { return "Stop capture" }
        return "Start capture"
    }

    private var captureIcon: String {
        if state.isWorking { return "hourglass" }
        return state.isCapturing ? "stop.circle.fill" : "record.circle"
    }

    private var captureSubtitle: String {
        if state.isWorking { return "Applying changes" }
        if state.isCapturing, state.systemProxyEnabled { return "Capturing traffic from this Mac" }
        if state.isCapturing { return "Listening on 127.0.0.1:\(state.port)" }
        return state.captureMode == .device
            ? "Routes this Mac through rae automatically"
            : "Only records apps configured to use the proxy"
    }

    private var captureButtonForeground: Color {
        if state.isCapturing { return .red }
        return .accentColor
    }

    private var captureButtonBackground: LinearGradient {
        LinearGradient(
            colors: [
                captureButtonForeground.opacity(0.18),
                captureButtonForeground.opacity(0.08),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var statusLine: String {
        if state.isCapturing, state.systemProxyEnabled { return "Recording this Mac" }
        if state.isCapturing { return "Manual proxy active" }
        return "Ready to capture"
    }
}

private struct SidebarSectionLabel: View {
    let title: String

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
    }
}

private struct CaptureModePicker: View {
    @Binding var selection: AppState.CaptureMode

    var body: some View {
        HStack(spacing: 8) {
            CaptureModeButton(
                title: "This Mac",
                detail: "Route device traffic",
                systemImage: "desktopcomputer",
                isSelected: selection == .device
            ) {
                selection = .device
            }
            CaptureModeButton(
                title: "Manual",
                detail: "Use proxy address",
                systemImage: "point.topleft.down.curvedto.point.bottomright.up",
                isSelected: selection == .manual
            ) {
                selection = .manual
            }
        }
    }
}

private struct CaptureModeButton: View {
    let title: String
    let detail: String
    let systemImage: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: systemImage)
                        .font(.system(size: 14, weight: .semibold))
                    Spacer()
                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 13, weight: .semibold))
                    }
                }
                Text(title)
                    .font(.callout.weight(.semibold))
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            .padding(10)
            .frame(maxWidth: .infinity, minHeight: 94, alignment: .topLeading)
            .foregroundStyle(isSelected ? Color.primary : Color.secondary)
            .background(isSelected ? Color.accentColor.opacity(0.14) : Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
            .overlay {
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? Color.accentColor.opacity(0.55) : Color.primary.opacity(0.05), lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
    }
}

private struct SidebarStatusRow: View {
    let title: String
    let detail: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.callout.weight(.medium))
                    .lineLimit(1)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
        }
        .padding(10)
        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 9))
    }
}

private struct SidebarActionLabel: View {
    let title: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .frame(width: 22)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.callout)
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
    }
}
