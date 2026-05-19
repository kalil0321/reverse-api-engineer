import AppKit
import SwiftUI
import ReverseAPIProxy

struct InspectorView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        if let id = state.selectedFlowID, let flow = state.store.flow(id: id) {
            FlowInspector(flow: flow)
        } else {
            VStack(spacing: 16) {
                ZStack {
                    RoundedRectangle(cornerRadius: 18)
                        .fill(Color.primary.opacity(0.055))
                        .frame(width: 70, height: 70)
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 30, weight: .medium))
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 6) {
                    Text("No request selected")
                        .font(.title3.weight(.semibold))
                    Text("Pick a row from traffic to inspect headers, timing, and body data.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 330)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
            .overlay {
                RoundedRectangle(cornerRadius: 10)
                    .stroke(.separator.opacity(0.5), lineWidth: 1)
            }
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
                    .padding(14)
            }
        }
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(.separator.opacity(0.5), lineWidth: 1)
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
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
                Text(TrafficFilter.resourceKind(for: flow).rawValue)
                    .font(.system(.caption, design: .monospaced).weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 5))
                Spacer()
                if let finishedAt = flow.finishedAt {
                    Text(formatDuration(flow.startedAt, finishedAt))
                        .foregroundStyle(.secondary)
                        .font(.callout)
                }
                copyMenu
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(flow.host)
                    .font(.headline)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(flow.url)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
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

    private var copyMenu: some View {
        Menu {
            Button("Copy request", systemImage: "arrow.up.doc") {
                copyToPasteboard(requestCopyText)
            }
            Button("Copy response", systemImage: "arrow.down.doc") {
                copyToPasteboard(responseCopyText)
            }
            Divider()
            Button("Copy URL", systemImage: "link") {
                copyToPasteboard(flow.url)
            }
        } label: {
            Label("Copy", systemImage: "doc.on.doc")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("Copy this request or response")
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .overview:
            overview
        case .request:
            VStack(alignment: .leading, spacing: 12) {
                HeadersSection(title: "Request headers", headers: flow.requestHeaders)
                BodySection(title: "Request body", bodyData: flow.requestBody, headers: flow.requestHeaders)
            }
        case .response:
            VStack(alignment: .leading, spacing: 12) {
                HeadersSection(title: "Response headers", headers: flow.responseHeaders)
                BodySection(title: "Response body", bodyData: flow.responseBody, headers: flow.responseHeaders)
            }
        }
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: 12) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 10)], spacing: 10) {
                MetricCard(title: "Status", value: flow.responseStatus.map(String.init) ?? "Pending")
                MetricCard(title: "Duration", value: durationValue)
                MetricCard(title: "Request", value: byteString(flow.requestBody.count))
                MetricCard(title: "Response", value: byteString(flow.responseBody.count))
            }

            DetailPanel(title: "Request") {
                row("Scheme", flow.scheme.rawValue)
                row("Host", "\(flow.host):\(flow.port)")
                row("Path", flow.path)
                row("Method", flow.method)
            }

            DetailPanel(title: "Timing") {
                row("Started", flow.startedAt.formatted(date: .abbreviated, time: .standard))
                row("Finished", flow.finishedAt?.formatted(date: .abbreviated, time: .standard) ?? "Pending")
            }
        }
    }

    private func row(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(key)
                .frame(width: 120, alignment: .leading)
                .foregroundStyle(.secondary)
            Text(value)
                .textSelection(.enabled)
                .font(.system(.callout, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)
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

    private var durationValue: String {
        guard let finishedAt = flow.finishedAt else { return "Pending" }
        return formatDuration(flow.startedAt, finishedAt)
    }

    private func byteString(_ count: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(count))
    }

    private var requestCopyText: String {
        var lines = ["\(flow.method) \(flow.path) HTTP/1.1"]
        lines.append(contentsOf: headerLines(flow.requestHeaders))
        return copyText(headLines: lines, body: flow.requestBody, headers: flow.requestHeaders)
    }

    private var responseCopyText: String {
        var lines = ["HTTP/1.1 \(flow.responseStatus.map(String.init) ?? "pending")"]
        lines.append(contentsOf: headerLines(flow.responseHeaders))
        return copyText(headLines: lines, body: flow.responseBody, headers: flow.responseHeaders)
    }

    private func headerLines(_ headers: [HTTPHeader]) -> [String] {
        headers.map { "\($0.name): \($0.value)" }
    }

    private func copyText(headLines: [String], body: Data, headers: [HTTPHeader]) -> String {
        guard !body.isEmpty else {
            return headLines.joined(separator: "\n") + "\n\n"
        }
        let bodyText = copyableBody(body, headers: headers)
        return headLines.joined(separator: "\n") + "\n\n" + bodyText
    }

    private func copyableBody(_ data: Data, headers: [HTTPHeader]) -> String {
        if let pretty = JSONFormatter.prettyPrintJSON(data, contentType: contentType(in: headers)) {
            return pretty
        }
        if let text = String(data: data, encoding: .utf8), looksLikeText(headers) {
            return text
        }
        return """
        Binary body: \(data.count) bytes
        Base64:
        \(data.base64EncodedString())
        """
    }

    private func contentType(in headers: [HTTPHeader]) -> String? {
        headers.first(where: { $0.name.lowercased() == "content-type" })?.value
    }

    private func looksLikeText(_ headers: [HTTPHeader]) -> Bool {
        guard let ct = contentType(in: headers)?.lowercased() else { return false }
        return ct.contains("text") || ct.contains("xml") || ct.contains("javascript") || ct.contains("html")
    }

    private func copyToPasteboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

private struct MetricCard: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(.callout, design: .monospaced).weight(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct DetailPanel<Content: View>: View {
    let title: String
    let content: Content

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            VStack(alignment: .leading, spacing: 8) {
                content
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
        }
    }
}

private struct HeadersSection: View {
    let title: String
    let headers: [HTTPHeader]

    var body: some View {
        DetailPanel(title: title) {
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
    }
}

private struct BodySection: View {
    let title: String
    let bodyData: Data
    let headers: [HTTPHeader]

    var body: some View {
        DetailPanel(title: title) {
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
