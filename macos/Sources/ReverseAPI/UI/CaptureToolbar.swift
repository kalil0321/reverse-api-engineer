import SwiftUI

struct CaptureToolbar: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var bindable = state

        return VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 16) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("ReverseAPI")
                        .font(.system(.title2, design: .rounded).weight(.semibold))
                    Text(statusLine)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 24)

                MetricPill(title: "Flows", value: "\(state.store.flows.count)")
                MetricPill(title: "Proxy", value: ":\(state.port)")
                ReadinessPill(
                    title: state.caTrustInstalled ? "CA trusted" : "CA not trusted",
                    systemImage: state.caTrustInstalled ? "checkmark.seal.fill" : "seal",
                    tint: state.caTrustInstalled ? .green : .orange
                )
            }

            HStack(spacing: 10) {
                Picker("Capture mode", selection: $bindable.captureMode) {
                    ForEach(AppState.CaptureMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 190)
                .disabled(state.isCapturing || state.isWorking)
                .help("Device captures traffic from this Mac. Manual only records clients explicitly configured to use 127.0.0.1:\(state.port).")

                captureButton
                trustButton
                systemProxyButton

                Spacer()

                if let error = state.lastError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(maxWidth: 420, alignment: .trailing)
                }

                Button("Clear", systemImage: "trash") {
                    state.clearFlows()
                }
                .buttonStyle(.borderless)
                .disabled(state.store.flows.isEmpty || state.isWorking)
                .help("Remove captured flows from the list and local database")
            }

            CaptureReadinessStrip()
        }
        .padding(.horizontal, 18)
        .padding(.top, 16)
        .padding(.bottom, 14)
        .background(.bar)
    }

    private var captureButton: some View {
        Button {
            Task { await state.toggleCapture() }
        } label: {
            Label(captureTitle, systemImage: captureIcon)
                .font(.headline)
                .frame(minWidth: 176)
        }
        .buttonStyle(.borderedProminent)
        .tint(state.isCapturing ? .red.opacity(0.85) : .accentColor)
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
            Label(
                state.caTrustInstalled ? "Trusted" : "Trust CA",
                systemImage: state.caTrustInstalled ? "checkmark.seal.fill" : "seal"
            )
        }
        .buttonStyle(.bordered)
        .disabled(state.isWorking)
        .help(state.caTrustInstalled
              ? "Remove the ReverseAPI root certificate from the current user's trust store"
              : "Trust the ReverseAPI root certificate so HTTPS requests can be inspected")
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
            Label(
                state.systemProxyEnabled ? "Device routed" : "Route device",
                systemImage: state.systemProxyEnabled ? "network.badge.shield.half.filled" : "network"
            )
        }
        .buttonStyle(.bordered)
        .disabled(state.isWorking || (state.isCapturing && state.captureMode == .device))
        .help("Toggle macOS HTTP/HTTPS proxy for active network services")
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
        if state.isCapturing, state.systemProxyEnabled {
            return "Recording traffic from this Mac. Proxy settings restore when capture stops."
        }
        if state.isCapturing {
            return "Manual proxy is listening at 127.0.0.1:\(state.port). Device traffic is not routed."
        }
        return "Device mode starts the proxy and routes this Mac in one step."
    }
}

private struct CaptureReadinessStrip: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 8) {
            ReadinessPill(
                title: state.isCapturing ? "Proxy running" : "Proxy stopped",
                systemImage: state.isCapturing ? "record.circle.fill" : "record.circle",
                tint: state.isCapturing ? .green : .secondary
            )
            ReadinessPill(
                title: state.systemProxyEnabled ? "Device traffic routed" : "Device traffic not routed",
                systemImage: state.systemProxyEnabled ? "arrow.triangle.branch" : "point.topleft.down.curvedto.point.bottomright.up",
                tint: state.systemProxyEnabled ? .green : .orange
            )
            ReadinessPill(
                title: state.caTrustInstalled ? "HTTPS inspectable" : "HTTPS needs CA trust",
                systemImage: state.caTrustInstalled ? "lock.open.fill" : "lock.fill",
                tint: state.caTrustInstalled ? .green : .orange
            )
            Spacer()
            Text(state.captureMode == .manual ? "Manual clients must use 127.0.0.1:\(state.port)." : "Recommended for normal testing.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

private struct MetricPill: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .trailing, spacing: 1) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(.callout, design: .monospaced).weight(.semibold))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 7))
    }
}

private struct ReadinessPill: View {
    let title: String
    let systemImage: String
    let tint: Color

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.medium))
            .foregroundStyle(tint)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 7))
    }
}
