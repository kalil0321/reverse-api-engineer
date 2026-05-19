import SwiftUI
import ReverseAPIProxy

struct InspectorView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        if let id = state.selectedFlowID, let flow = state.store.flow(id: id) {
            FlowInspector(flow: flow)
        } else {
            VStack(spacing: 12) {
                Image(systemName: "sidebar.right")
                    .font(.system(size: 36))
                    .foregroundStyle(.secondary)
                Text("Select a flow")
                    .font(.title3.weight(.semibold))
                Text("Request headers, response data, timing, and body previews appear here.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 340)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
    }
}

private struct FlowInspector: View {
    let flow: CapturedFlow
    @State private var tab: InspectorTab = .request

    enum InspectorTab: String, CaseIterable, Identifiable {
        case overview = "Overview"
        case request = "Request"
        case response = "Response"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Picker("", selection: $tab) {
                ForEach(InspectorTab.allCases) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            Divider()
            ScrollView {
                content
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
        }
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(flow.method)
                    .font(.system(.callout, design: .monospaced).weight(.semibold))
                    .foregroundStyle(methodColor)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(methodColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 5))
                if let status = flow.responseStatus {
                    Text("\(status)")
                        .font(.system(.callout, design: .monospaced).weight(.semibold))
                        .foregroundStyle(statusColor(status))
                }
                Spacer()
                if let finishedAt = flow.finishedAt {
                    Text(formatDuration(flow.startedAt, finishedAt))
                        .foregroundStyle(.secondary)
                        .font(.callout)
                }
            }
            Text(flow.url)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
                .lineLimit(2)
                .truncationMode(.middle)
            if let error = flow.error {
                Label(error, systemImage: "exclamationmark.octagon.fill")
                    .foregroundStyle(.red)
                    .font(.callout)
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 10)
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .overview:
            overview
        case .request:
            HeadersSection(title: "Request headers", headers: flow.requestHeaders)
            BodySection(title: "Request body", bodyData: flow.requestBody, headers: flow.requestHeaders)
        case .response:
            HeadersSection(title: "Response headers", headers: flow.responseHeaders)
            BodySection(title: "Response body", bodyData: flow.responseBody, headers: flow.responseHeaders)
        }
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: 8) {
            row("Scheme", flow.scheme.rawValue)
            row("Host", "\(flow.host):\(flow.port)")
            row("Path", flow.path)
            row("Method", flow.method)
            row("Status", flow.responseStatus.map(String.init) ?? "—")
            row("Started", flow.startedAt.formatted(date: .abbreviated, time: .standard))
            row("Finished", flow.finishedAt?.formatted(date: .abbreviated, time: .standard) ?? "—")
            row("Request size", "\(flow.requestBody.count) bytes")
            row("Response size", "\(flow.responseBody.count) bytes")
        }
    }

    private func row(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(key)
                .frame(width: 120, alignment: .leading)
                .foregroundStyle(.secondary)
            Text(value)
                .textSelection(.enabled)
                .font(.system(.body, design: .monospaced))
        }
    }

    private func formatDuration(_ start: Date, _ end: Date) -> String {
        let interval = end.timeIntervalSince(start)
        if interval < 1 { return String(format: "%.0f ms", interval * 1000) }
        return String(format: "%.2f s", interval)
    }

    private var methodColor: Color {
        switch flow.method {
        case "GET": return .blue
        case "POST": return .green
        case "PUT", "PATCH": return .orange
        case "DELETE": return .red
        default: return .secondary
        }
    }

    private func statusColor(_ status: Int) -> Color {
        switch status {
        case 200..<300: return .green
        case 300..<400: return .blue
        case 400..<500: return .orange
        case 500..<600: return .red
        default: return .secondary
        }
    }
}

private struct HeadersSection: View {
    let title: String
    let headers: [HTTPHeader]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            if headers.isEmpty {
                Text("No headers")
                    .foregroundStyle(.tertiary)
                    .font(.callout)
            } else {
                ForEach(Array(headers.enumerated()), id: \.offset) { _, header in
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(header.name)
                            .font(.system(.callout, design: .monospaced).weight(.semibold))
                            .foregroundStyle(.secondary)
                            .frame(width: 160, alignment: .leading)
                        Text(header.value)
                            .font(.system(.callout, design: .monospaced))
                            .textSelection(.enabled)
                            .lineLimit(nil)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }
        .padding(.bottom, 16)
    }
}

private struct BodySection: View {
    let title: String
    let bodyData: Data
    let headers: [HTTPHeader]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            if bodyData.isEmpty {
                Text("Empty body")
                    .foregroundStyle(.tertiary)
                    .font(.callout)
            } else if let pretty = JSONFormatter.prettyPrintJSON(bodyData, contentType: contentType) {
                CodeBlock(text: pretty)
            } else if let text = String(data: bodyData, encoding: .utf8), looksLikeText {
                CodeBlock(text: text)
            } else {
                Text("Binary content · \(bodyData.count) bytes")
                    .foregroundStyle(.secondary)
                    .font(.callout)
            }
        }
    }

    private var contentType: String? {
        headers.first(where: { $0.name.lowercased() == "content-type" })?.value
    }

    private var looksLikeText: Bool {
        guard let ct = contentType?.lowercased() else { return false }
        return ct.contains("text") || ct.contains("xml") || ct.contains("javascript") || ct.contains("html")
    }
}

private struct CodeBlock: View {
    let text: String

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            Text(text)
                .font(.system(.callout, design: .monospaced))
                .textSelection(.enabled)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Color(nsColor: .textBackgroundColor).opacity(0.62), in: RoundedRectangle(cornerRadius: 6))
        .overlay {
            RoundedRectangle(cornerRadius: 6)
                .stroke(.separator.opacity(0.45), lineWidth: 1)
        }
    }
}
