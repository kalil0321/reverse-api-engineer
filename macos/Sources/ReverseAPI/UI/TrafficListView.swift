import AppKit
import SwiftUI
import ReverseAPIProxy

struct TrafficListView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(spacing: 0) {
                TrafficHeaderRow()
                ThinDivider()
                if state.store.flows.isEmpty {
                    EmptyTrafficState()
                } else if filteredFlows.isEmpty {
                    EmptyFilterState()
                } else {
                    TrafficRowList(flows: filteredFlows)
                }
            }
        }
    }

    private var filteredFlows: [CapturedFlow] {
        state.store.flows.filter { state.filter.matches($0) }
    }
}

// MARK: - Header

private struct TrafficHeaderRow: View {
    var body: some View {
        HStack(spacing: 0) {
            HeaderLabel("Time", width: 72, align: .leading)
            HeaderLabel("Method", width: 64, align: .leading)
            HeaderLabel("Host", width: 200, align: .leading)
            HeaderLabel("Path", width: nil, align: .leading)
            HeaderLabel("Status", width: 60, align: .trailing)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(Theme.appBackground)
    }
}

private struct HeaderLabel: View {
    let text: String
    let width: CGFloat?
    let align: Alignment

    init(_ text: String, width: CGFloat?, align: Alignment) {
        self.text = text
        self.width = width
        self.align = align
    }

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(Theme.textTertiary)
            .tracking(0.6)
            .frame(width: width, alignment: align)
            .frame(maxWidth: width == nil ? .infinity : nil, alignment: align)
    }
}

// MARK: - Rows

private struct TrafficRowList: View {
    @Environment(AppState.self) private var state
    let flows: [CapturedFlow]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(flows) { flow in
                        TrafficRow(
                            flow: flow,
                            isSelected: state.selectedFlowID == flow.id
                        ) {
                            state.selectedFlowID = flow.id
                        }
                        .id(flow.id)
                    }
                }
            }
            .onChange(of: state.selectedFlowID) { _, new in
                guard let new else { return }
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo(new, anchor: .center)
                }
            }
        }
    }
}

private struct TrafficRow: View {
    let flow: CapturedFlow
    let isSelected: Bool
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 0) {
                Text(flow.startedAt, format: .dateTime.hour().minute().second())
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 72, alignment: .leading)

                MethodBadge(method: flow.method)
                    .frame(width: 64, alignment: .leading)

                Text(flow.host)
                    .font(.callout)
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(width: 200, alignment: .leading)

                Text(flow.path)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading)

                StatusBadge(status: flow.responseStatus, error: flow.error)
                    .frame(width: 60, alignment: .trailing)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity)
            .background(background)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
        }
    }

    private var background: Color {
        if isSelected { return Theme.elevated }
        if isHovering { return Color.white.opacity(0.03) }
        return Color.clear
    }
}

private struct MethodBadge: View {
    let method: String

    var body: some View {
        Text(method)
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(color)
    }

    private var color: Color {
        switch method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        case "CONNECT": return Theme.methodConnect
        default: return Theme.textSecondary
        }
    }
}

private struct StatusBadge: View {
    let status: Int?
    let error: String?

    var body: some View {
        if let error {
            Text("ERR")
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .foregroundStyle(Theme.danger)
                .help(error)
        } else if let status {
            Text("\(status)")
                .font(.system(.callout, design: .monospaced).weight(.medium))
                .foregroundStyle(color(for: status))
        } else {
            Text("…")
                .foregroundStyle(Theme.textTertiary)
        }
    }

    private func color(for status: Int) -> Color {
        switch status {
        case 200..<300: return Theme.success
        case 300..<400: return Theme.methodGet
        case 400..<500: return Theme.methodPut
        case 500..<600: return Theme.danger
        default: return Theme.textSecondary
        }
    }
}

// MARK: - Empty states

private struct EmptyTrafficState: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: state.isCapturing ? "dot.radiowaves.left.and.right" : "waveform.path.ecg")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Theme.textTertiary)

            VStack(spacing: 4) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text(message)
                    .font(.callout)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var title: String {
        if state.isCapturing, !state.systemProxyEnabled { return "Manual capture is running" }
        if state.isCapturing { return "Waiting for traffic" }
        return "No traffic captured"
    }

    private var message: String {
        if state.isCapturing, !state.systemProxyEnabled {
            return "Only clients configured to use the proxy will appear here."
        }
        if state.isCapturing, !state.caTrustInstalled {
            return "HTTP shows up immediately. Trust the CA to inspect HTTPS."
        }
        if state.isCapturing {
            return "Open an app or browser to make a request."
        }
        return "Press Record to start capturing."
    }
}

private struct EmptyFilterState: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(Theme.textTertiary)
            Text("No matching traffic")
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            Text("Clear or loosen the current filters.")
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
