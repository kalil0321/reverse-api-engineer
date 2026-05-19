import SwiftUI

struct CaptureToolbar: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 12) {
            captureButton
            Divider().frame(height: 18)
            trustButton
            systemProxyButton
            Spacer()
            statusText
            Button("Clear", systemImage: "trash") {
                state.clearFlows()
            }
            .buttonStyle(.borderless)
            .help("Remove all captured flows")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private var captureButton: some View {
        Button {
            Task { await state.toggleCapture() }
        } label: {
            Label(
                state.isCapturing ? "Capturing" : "Start capture",
                systemImage: state.isCapturing ? "stop.circle.fill" : "record.circle"
            )
            .foregroundStyle(state.isCapturing ? Color.red : Color.primary)
            .font(.headline)
        }
        .buttonStyle(.borderedProminent)
        .tint(state.isCapturing ? .red.opacity(0.85) : .accentColor)
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
                state.caTrustInstalled ? "CA trusted" : "Install CA",
                systemImage: state.caTrustInstalled ? "checkmark.seal.fill" : "seal"
            )
        }
        .buttonStyle(.bordered)
        .help(state.caTrustInstalled
              ? "Remove the ReverseAPI root certificate from the user keychain"
              : "Install the ReverseAPI root certificate as trusted for the current user")
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
                state.systemProxyEnabled ? "System proxy on" : "System proxy off",
                systemImage: state.systemProxyEnabled ? "network.badge.shield.half.filled" : "network"
            )
        }
        .buttonStyle(.bordered)
        .help("Toggle macOS HTTP/HTTPS proxy on every active network service")
    }

    private var statusText: some View {
        Group {
            if let error = state.lastError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                    .lineLimit(1)
                    .truncationMode(.middle)
            } else {
                Text("\(state.store.flows.count) flows · 127.0.0.1:\(state.port)")
                    .foregroundStyle(.secondary)
            }
        }
        .font(.callout)
    }
}
