import AppKit
import SwiftUI
import WebKit
import ReverseAPIProxy

struct InspectorView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        if let id = state.selectedFlowID, let flow = state.store.flow(id: id) {
            FlowInspector(flow: flow)
        } else {
            EmptyInspector()
        }
    }
}

private struct EmptyInspector: View {
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Theme.textTertiary)
            Text("No request selected")
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            Text("Pick a row from the traffic list.")
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.surface)
    }
}

enum InspectorTab: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case request = "Request"
    case response = "Response"
    case preview = "Preview"
    var id: String { rawValue }
}

private struct FlowInspector: View {
    let flow: CapturedFlow
    @State private var tab: InspectorTab = .request
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            ThinDivider()
            tabBar
            ThinDivider()
            ScrollView {
                content
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
        }
        .background(Theme.surface)
        .onChange(of: flow.id) { _, _ in
            // Reset tab when switching selection, fallback if current tab no longer available
            if !availableTabs.contains(tab) {
                tab = .request
            }
        }
    }

    private var tabBar: some View {
        HStack {
            NSSegmented(
                labels: availableTabs.map { $0.rawValue },
                selection: Binding(
                    get: { availableTabs.firstIndex(of: tab) ?? 0 },
                    set: { tab = availableTabs[$0] }
                )
            )
            .fixedSize()
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private var availableTabs: [InspectorTab] {
        var tabs: [InspectorTab] = [.overview, .request, .response]
        if previewKind != nil { tabs.append(.preview) }
        return tabs
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Text(flow.method)
                    .font(.system(.callout, design: .monospaced).weight(.semibold))
                    .foregroundStyle(methodColor)
                if let status = flow.responseStatus {
                    Text("\(status)")
                        .font(.system(.callout, design: .monospaced).weight(.semibold))
                        .foregroundStyle(statusColor(status))
                }
                Spacer()
                if let finishedAt = flow.finishedAt {
                    Text(formatDuration(flow.startedAt, finishedAt))
                        .foregroundStyle(Theme.textSecondary)
                        .font(.caption)
                        .monospacedDigit()
                }
                copyMenu
                Button {
                    state.selectedFlowID = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("Close inspector")
            }

            Text(flow.url)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)
                .lineLimit(2)
                .truncationMode(.middle)

            if let error = flow.error {
                Label(error, systemImage: "exclamationmark.octagon.fill")
                    .foregroundStyle(Theme.danger)
                    .font(.caption)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 14)
        .padding(.bottom, 12)
    }

    private var copyMenu: some View {
        Menu {
            Button("Copy request") { copyToPasteboard(requestCopyText) }
            Button("Copy response") { copyToPasteboard(responseCopyText) }
            Divider()
            Button("Copy URL") { copyToPasteboard(flow.url) }
        } label: {
            Image(systemName: "doc.on.doc")
                .foregroundStyle(Theme.textSecondary)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("Copy")
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .overview:
            overview
        case .request:
            VStack(alignment: .leading, spacing: 18) {
                HeadersSection(title: "Headers", headers: flow.requestHeaders)
                BodySection(title: "Body", bodyData: flow.requestBody, headers: flow.requestHeaders)
            }
        case .response:
            VStack(alignment: .leading, spacing: 18) {
                HeadersSection(title: "Headers", headers: flow.responseHeaders)
                BodySection(title: "Body", bodyData: flow.responseBody, headers: flow.responseHeaders)
            }
        case .preview:
            if let kind = previewKind {
                PreviewPaneContent(
                    data: flow.responseBody,
                    kind: kind,
                    flowURL: flow.url,
                    contentType: responseHeader("content-type")
                )
            } else {
                Text("Nothing to preview")
                    .foregroundStyle(Theme.textTertiary)
                    .font(.callout)
            }
        }
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: 18) {
            Section(label: "Request") {
                row("Scheme", flow.scheme.rawValue)
                row("Host", "\(flow.host):\(flow.port)")
                row("Method", flow.method)
                row("Path", flow.path)
            }

            Section(label: "Response") {
                row("Status", flow.responseStatus.map(String.init) ?? "pending")
                row("Type", TrafficFilter.resourceKind(for: flow).rawValue)
                row("Content-Type", responseHeader("content-type") ?? "—")
                row("Encoding", responseHeader("content-encoding") ?? "—")
                row("Size", byteString(flow.responseBody.count))
            }

            Section(label: "Timing") {
                row("Started", flow.startedAt.formatted(date: .abbreviated, time: .standard))
                row("Finished", flow.finishedAt?.formatted(date: .abbreviated, time: .standard) ?? "pending")
                if let finished = flow.finishedAt {
                    row("Duration", formatDuration(flow.startedAt, finished))
                }
            }
        }
    }

    private func row(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(key)
                .frame(width: 100, alignment: .leading)
                .foregroundStyle(Theme.textSecondary)
                .font(.callout)
            Text(value)
                .textSelection(.enabled)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Preview availability

    private var previewKind: PreviewKind? {
        guard let ct = responseHeader("content-type")?.lowercased() else { return nil }
        if ct.hasPrefix("image/") && NSImage(data: flow.responseBody) != nil { return .image }
        if ct.contains("html") { return .html }
        if ct.contains("pdf") { return .pdf }
        return nil
    }

    private func responseHeader(_ name: String) -> String? {
        flow.responseHeaders.first(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame })?.value
    }

    // MARK: - Helpers

    private func formatDuration(_ start: Date, _ end: Date) -> String {
        let interval = end.timeIntervalSince(start)
        if interval < 1 { return String(format: "%.0f ms", interval * 1000) }
        return String(format: "%.2f s", interval)
    }

    private var methodColor: Color {
        switch flow.method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        default: return Theme.textSecondary
        }
    }

    private func statusColor(_ status: Int) -> Color {
        switch status {
        case 200..<300: return Theme.success
        case 300..<400: return Theme.methodGet
        case 400..<500: return Theme.methodPut
        case 500..<600: return Theme.danger
        default: return Theme.textSecondary
        }
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
        let ct = headers.first(where: { $0.name.caseInsensitiveCompare("content-type") == .orderedSame })?.value
        if let pretty = JSONFormatter.prettyPrintJSON(data, contentType: ct) {
            return pretty
        }
        if let text = String(data: data, encoding: .utf8), let ct, ct.lowercased().contains("text") {
            return text
        }
        return """
        Binary body: \(data.count) bytes
        Base64:
        \(data.base64EncodedString())
        """
    }

    private func copyToPasteboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

// MARK: - Preview kinds

enum PreviewKind {
    case image
    case html
    case pdf
}

private struct PreviewPaneContent: View {
    let data: Data
    let kind: PreviewKind
    let flowURL: String
    let contentType: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            previewBadge
            content
        }
    }

    private var previewBadge: some View {
        HStack(spacing: 6) {
            Image(systemName: badgeIcon)
                .font(.caption)
                .foregroundStyle(Theme.textTertiary)
            Text(badgeLabel)
                .font(.caption)
                .foregroundStyle(Theme.textTertiary)
            Spacer()
        }
    }

    @ViewBuilder
    private var content: some View {
        switch kind {
        case .image:
            ImagePreview(data: data)
        case .html:
            HTMLPreview(data: data, baseURL: URL(string: flowURL))
        case .pdf:
            PDFPreview(data: data)
        }
    }

    private var badgeIcon: String {
        switch kind {
        case .image: return "photo"
        case .html: return "doc.richtext"
        case .pdf: return "doc"
        }
    }

    private var badgeLabel: String {
        contentType ?? {
            switch kind {
            case .image: return "image"
            case .html: return "text/html"
            case .pdf: return "application/pdf"
            }
        }()
    }
}

private struct ImagePreview: View {
    let data: Data

    var body: some View {
        if let image = NSImage(data: data) {
            VStack(spacing: 8) {
                ZStack {
                    CheckerboardPattern()
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    Image(nsImage: image)
                        .interpolation(.none)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: maxDisplayWidth(for: image), maxHeight: maxDisplayHeight(for: image))
                        .padding(8)
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: 220, idealHeight: 360)
                .overlay {
                    RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
                }
                metaLine(for: image)
            }
        } else {
            Text("Could not decode image data")
                .foregroundStyle(Theme.textTertiary)
                .font(.callout)
        }
    }

    private func metaLine(for image: NSImage) -> some View {
        HStack(spacing: 8) {
            Text("\(Int(image.size.width)) × \(Int(image.size.height))")
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(Theme.textTertiary)
            if isTinyTracker(image) {
                Text("tracking pixel")
                    .font(.caption)
                    .foregroundStyle(Theme.textTertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Theme.elevated, in: Capsule())
            }
            Spacer()
        }
    }

    /// Avoid stretching tiny images to fill the preview — pixelated upscaling
    /// destroys context. Cap them at 256pt so they remain readable.
    private func maxDisplayWidth(for image: NSImage) -> CGFloat? {
        guard image.size.width > 0, image.size.width <= 64 else { return nil }
        return min(image.size.width * 16, 256)
    }

    private func maxDisplayHeight(for image: NSImage) -> CGFloat? {
        guard image.size.height > 0, image.size.height <= 64 else { return nil }
        return min(image.size.height * 16, 256)
    }

    private func isTinyTracker(_ image: NSImage) -> Bool {
        image.size.width <= 4 && image.size.height <= 4
    }
}

/// Photoshop-style checkered transparency background — two visibly distinct
/// gray tiles so transparent/very-small images stay legible on a dark theme.
private struct CheckerboardPattern: View {
    var body: some View {
        Canvas { context, size in
            let tileSize: CGFloat = 12
            let cols = Int(ceil(size.width / tileSize))
            let rows = Int(ceil(size.height / tileSize))
            let lightTile = Color.white.opacity(0.07)
            let darkTile = Color.white.opacity(0.02)
            for r in 0..<rows {
                for c in 0..<cols {
                    let rect = CGRect(
                        x: CGFloat(c) * tileSize,
                        y: CGFloat(r) * tileSize,
                        width: tileSize,
                        height: tileSize
                    )
                    let color = (r + c) % 2 == 0 ? lightTile : darkTile
                    context.fill(Path(rect), with: .color(color))
                }
            }
        }
    }
}

private struct HTMLPreview: NSViewRepresentable {
    let data: Data
    let baseURL: URL?

    func makeNSView(context: Context) -> NSView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.appearance = NSAppearance(named: .darkAqua)

        let container = NSView()
        container.wantsLayer = true
        container.layer?.cornerRadius = 8
        container.layer?.borderColor = NSColor.white.withAlphaComponent(0.07).cgColor
        container.layer?.borderWidth = 1
        container.layer?.masksToBounds = true

        webView.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            container.heightAnchor.constraint(greaterThanOrEqualToConstant: 360),
        ])
        loadContent(into: webView)
        context.coordinator.webView = webView
        return container
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let webView = context.coordinator.webView else { return }
        if context.coordinator.lastData != data {
            loadContent(into: webView)
            context.coordinator.lastData = data
        }
    }

    private func loadContent(into webView: WKWebView) {
        let html = String(data: data, encoding: .utf8) ?? ""
        webView.loadHTMLString(html, baseURL: baseURL)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var webView: WKWebView?
        var lastData: Data?
    }
}

private struct PDFPreview: View {
    let data: Data

    var body: some View {
        Text("PDF preview is not yet supported. Use the response body to inspect raw bytes.")
            .font(.callout)
            .foregroundStyle(Theme.textSecondary)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Existing sections

private struct Section<Content: View>: View {
    let label: String
    let content: Content

    init(label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Theme.textTertiary)
                .tracking(0.7)
            VStack(alignment: .leading, spacing: 6) {
                content
            }
        }
    }
}

private struct HeadersSection: View {
    let title: String
    let headers: [HTTPHeader]

    var body: some View {
        Section(label: title) {
            if headers.isEmpty {
                Text("No headers")
                    .foregroundStyle(Theme.textTertiary)
                    .font(.callout)
            } else {
                ForEach(Array(headers.enumerated()), id: \.offset) { _, header in
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(header.name)
                            .font(.system(.callout, design: .monospaced).weight(.medium))
                            .foregroundStyle(Theme.textSecondary)
                            .frame(width: 150, alignment: .leading)
                        Text(header.value)
                            .font(.system(.callout, design: .monospaced))
                            .foregroundStyle(Theme.textPrimary)
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
        Section(label: title) {
            if bodyData.isEmpty {
                Text("Empty body")
                    .foregroundStyle(Theme.textTertiary)
                    .font(.callout)
            } else if let pretty = JSONFormatter.prettyPrintJSON(bodyData, contentType: contentType) {
                CodeBlock(text: pretty)
            } else if let text = String(data: bodyData, encoding: .utf8), looksLikeText {
                CodeBlock(text: text)
            } else if let text = String(data: bodyData, encoding: .utf8), isMostlyPrintable(text) {
                CodeBlock(text: text)
            } else {
                BinaryBodyNotice(
                    byteCount: bodyData.count,
                    contentType: contentType,
                    contentEncoding: contentEncoding
                )
            }
        }
    }

    private var contentType: String? {
        headers.first(where: { $0.name.lowercased() == "content-type" })?.value
    }

    private var contentEncoding: String? {
        headers.first(where: { $0.name.lowercased() == "content-encoding" })?.value
    }

    private var looksLikeText: Bool {
        guard let ct = contentType?.lowercased() else { return false }
        return ct.contains("text") ||
            ct.contains("json") ||
            ct.contains("xml") ||
            ct.contains("javascript") ||
            ct.contains("html") ||
            ct.contains("event-stream") ||
            ct.contains("x-www-form-urlencoded") ||
            ct.contains("graphql") ||
            ct.contains("csv")
    }

    private func isMostlyPrintable(_ text: String) -> Bool {
        guard !text.isEmpty else { return false }
        let scalars = text.unicodeScalars
        let printable = scalars.filter { scalar in
            scalar.value == 10 || scalar.value == 13 || scalar.value == 9 || scalar.value >= 32
        }
        return Double(printable.count) / Double(scalars.count) > 0.92
    }
}

private struct BinaryBodyNotice: View {
    let byteCount: Int
    let contentType: String?
    let contentEncoding: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Binary · \(byteCount) bytes", systemImage: "cube.transparent")
                .font(.callout)
                .foregroundStyle(Theme.textPrimary)
            Text(reason)
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let contentType {
                Text("Content-Type: \(contentType)")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
            }
            if let contentEncoding {
                Text("Content-Encoding: \(contentEncoding)")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
            }
        }
    }

    private var reason: String {
        if let contentEncoding, !contentEncoding.localizedCaseInsensitiveContains("identity") {
            return "Server returned an encoded body."
        }
        if let contentType, isKnownBinary(contentType) {
            return "Binary asset — no text preview available."
        }
        return "Could not decode body as JSON or readable text."
    }

    private func isKnownBinary(_ contentType: String) -> Bool {
        let lower = contentType.lowercased()
        return lower.hasPrefix("image/") ||
            lower.hasPrefix("audio/") ||
            lower.hasPrefix("video/") ||
            lower.contains("font") ||
            lower.contains("octet-stream") ||
            lower.contains("protobuf") ||
            lower.contains("msgpack")
    }
}

private struct CodeBlock: View {
    let text: String

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            Text(text)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.appBackground, in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
        }
    }
}
