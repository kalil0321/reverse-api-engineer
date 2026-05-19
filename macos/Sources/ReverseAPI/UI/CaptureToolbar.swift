import SwiftUI

struct CaptureToolbar: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var bindable = state

        return VStack(alignment: .leading, spacing: 18) {
            brandHeader

            VStack(spacing: 10) {
                captureButton
                Picker("Capture mode", selection: $bindable.captureMode) {
                    ForEach(AppState.CaptureMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .disabled(state.isCapturing || state.isWorking)
            }

            VStack(alignment: .leading, spacing: 8) {
                SidebarStatusRow(
                    title: state.isCapturing ? "Proxy running" : "Proxy stopped",
                    detail: "127.0.0.1:\(state.port)",
                    systemImage: "record.circle",
                    tint: state.isCapturing ? .green : .secondary
                )
                SidebarStatusRow(
                    title: state.systemProxyEnabled ? "Device routed" : "Device not routed",
                    detail: state.captureMode == .device ? "Automatic capture" : "Manual clients only",
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
                Text("Actions")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                trustButton
                systemProxyButton
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
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 9)
                        .fill(Color.accentColor.opacity(0.16))
                    Image(systemName: "waveform.path.ecg")
                        .foregroundStyle(Color.accentColor)
                        .font(.system(size: 17, weight: .semibold))
                }
                .frame(width: 34, height: 34)

                VStack(alignment: .leading, spacing: 1) {
                    Text("rae")
                        .font(.system(.title3, design: .rounded).weight(.semibold))
                    Text(statusLine)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
        }
    }

    private var captureButton: some View {
        Button {
            Task { await state.toggleCapture() }
        } label: {
            Label(captureTitle, systemImage: captureIcon)
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 5)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .tint(state.isCapturing ? .red.opacity(0.86) : .accentColor)
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
        return state.captureMode == .device ? "Start device capture" : "Start manual capture"
    }

    private var captureIcon: String {
        if state.isWorking { return "hourglass" }
        return state.isCapturing ? "stop.circle.fill" : "record.circle"
    }

    private var statusLine: String {
        if state.isCapturing, state.systemProxyEnabled { return "Recording this Mac" }
        if state.isCapturing { return "Manual proxy active" }
        return "Ready to capture"
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
