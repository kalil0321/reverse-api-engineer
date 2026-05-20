import SwiftUI
import AppKit
import ReverseAPIProxy

struct CommandPalette: View {
    @Environment(AppState.self) private var state
    @Binding var isPresented: Bool

    @State private var query: String = ""
    @State private var highlightedIndex: Int = 0
    @Namespace private var highlightNamespace

    var body: some View {
        VStack(spacing: 0) {
            queryHeader
            HStack(spacing: 0) {
                resultsList
                if let flow = highlightedFlow {
                    previewDivider
                    PreviewPane(flow: flow)
                }
            }
            .frame(maxHeight: .infinity)
        }
        .frame(width: 760, height: 480)
        .background {
            ZStack {
                VisualEffect(material: .underWindowBackground, blendingMode: .behindWindow)
                Theme.surface.opacity(0.86)
                topHighlight
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.55), radius: 40, x: 0, y: 18)
        .shadow(color: .black.opacity(0.35), radius: 6, x: 0, y: 3)
        .onChange(of: query) { _, _ in
            highlightedIndex = 0
        }
        .onKeyPress(.upArrow) {
            moveHighlight(-1)
            return .handled
        }
        .onKeyPress(.downArrow) {
            moveHighlight(1)
            return .handled
        }
        .onKeyPress(.escape) {
            dismiss()
            return .handled
        }
    }

    // MARK: - Subviews

    private var topHighlight: some View {
        VStack(spacing: 0) {
            LinearGradient(
                colors: [Color.white.opacity(0.05), Color.white.opacity(0)],
                startPoint: .top,
                endPoint: .bottom
            )
            .frame(height: 90)
            Spacer()
        }
    }

    private var queryHeader: some View {
        HStack(spacing: 14) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 18, weight: .medium))
                .foregroundStyle(Theme.textSecondary)

            NativeSearchField(
                text: $query,
                placeholder: "Search traffic",
                onSubmit: { select() }
            )
            .frame(maxWidth: .infinity)
            .frame(height: 28)

            if !query.isEmpty {
                Button {
                    query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(Theme.textTertiary)
                        .font(.system(size: 14))
                }
                .buttonStyle(.plain)
            }

            CountChip(count: results.count)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 18)
        .background(alignment: .bottom) {
            Rectangle().fill(Color.white.opacity(0.06)).frame(height: 1)
        }
    }

    private var resultsList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if results.isEmpty {
                        emptyState
                    } else {
                        ForEach(Array(results.enumerated()), id: \.element.id) { index, flow in
                            ResultRow(
                                flow: flow,
                                isHighlighted: index == highlightedIndex,
                                namespace: highlightNamespace,
                                onSelect: { pick(flow) }
                            )
                            .id(flow.id)
                            .onHover { hovering in
                                if hovering { highlightedIndex = index }
                            }
                        }
                    }
                }
                .padding(.vertical, 6)
                .padding(.horizontal, 8)
            }
            .frame(width: highlightedFlow != nil ? 380 : 760)
            .onChange(of: highlightedIndex) { _, new in
                guard new < results.count else { return }
                withAnimation(.easeOut(duration: 0.12)) {
                    proxy.scrollTo(results[new].id, anchor: .center)
                }
            }
        }
    }

    private var previewDivider: some View {
        Rectangle()
            .fill(Color.white.opacity(0.06))
            .frame(width: 1)
            .frame(maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: query.isEmpty ? "tray" : "questionmark.circle")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Theme.textTertiary)
            VStack(spacing: 4) {
                Text(query.isEmpty ? "Start typing to search" : "No matching traffic")
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text(query.isEmpty
                     ? "Search by host, path, method, or URL"
                     : "Try a different query")
                    .font(.callout)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 240)
    }

    private var footer: some View {
        HStack(spacing: 14) {
            FooterHint(symbols: ["↑", "↓"], label: "navigate")
            FooterHint(symbols: ["↵"], label: "open")
            FooterHint(symbols: ["esc"], label: "close")
            Spacer()
            if let flow = highlightedFlow {
                Text(flow.host)
                    .font(.caption)
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(alignment: .top) {
            Rectangle().fill(Color.white.opacity(0.06)).frame(height: 1)
        }
    }

    // MARK: - Data

    private var results: [CapturedFlow] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let all = state.store.flows.reversed()
        guard !trimmed.isEmpty else {
            return Array(all.prefix(50))
        }
        let needle = trimmed.lowercased()
        return all.filter { flow in
            flow.host.lowercased().contains(needle) ||
                flow.path.lowercased().contains(needle) ||
                flow.method.lowercased().contains(needle) ||
                flow.url.lowercased().contains(needle)
        }
    }

    private var highlightedFlow: CapturedFlow? {
        guard highlightedIndex < results.count else { return nil }
        return results[highlightedIndex]
    }

    // MARK: - Actions

    private func moveHighlight(_ delta: Int) {
        let count = results.count
        guard count > 0 else { return }
        withAnimation(.spring(response: 0.22, dampingFraction: 0.86)) {
            highlightedIndex = (highlightedIndex + delta + count) % count
        }
    }

    private func select() {
        guard let flow = highlightedFlow else { return }
        pick(flow)
    }

    private func pick(_ flow: CapturedFlow) {
        state.selectedFlowID = flow.id
        dismiss()
    }

    private func dismiss() {
        isPresented = false
    }
}

// MARK: - Result row

private struct ResultRow: View {
    let flow: CapturedFlow
    let isHighlighted: Bool
    let namespace: Namespace.ID
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            ZStack(alignment: .leading) {
                if isHighlighted {
                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .fill(Color.white.opacity(0.07))
                        .matchedGeometryEffect(id: "highlight", in: namespace)
                }
                HStack(spacing: 12) {
                    methodTag
                    statusTag
                    VStack(alignment: .leading, spacing: 2) {
                        Text(flow.host)
                            .font(.callout)
                            .foregroundStyle(Theme.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(flow.path)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Spacer(minLength: 8)
                    if isHighlighted {
                        Image(systemName: "return")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Theme.textTertiary)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
        }
        .buttonStyle(.plain)
    }

    private var methodTag: some View {
        Text(flow.method)
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(methodColor)
            .frame(width: 54, alignment: .leading)
    }

    @ViewBuilder
    private var statusTag: some View {
        if let status = flow.responseStatus {
            Text("\(status)")
                .font(.system(.caption, design: .monospaced).weight(.medium))
                .foregroundStyle(statusColor(status))
                .frame(width: 32, alignment: .leading)
        } else if flow.error != nil {
            Text("ERR")
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .foregroundStyle(Theme.danger)
                .frame(width: 32, alignment: .leading)
        } else {
            Text("…")
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 32, alignment: .leading)
        }
    }

    private var methodColor: Color {
        switch flow.method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        case "CONNECT": return Theme.methodConnect
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
}

// MARK: - Preview pane

private struct PreviewPane: View {
    let flow: CapturedFlow

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                detailGrid
                if let cType = headerValue("content-type") {
                    metaRow(label: "Content-Type", value: cType)
                }
                if let cEnc = headerValue("content-encoding") {
                    metaRow(label: "Encoding", value: cEnc)
                }
                if let error = flow.error {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(Theme.danger)
                            .font(.caption)
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(Theme.danger)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(width: 379)
        .background(Color.white.opacity(0.015))
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(flow.method)
                    .font(.system(.callout, design: .monospaced).weight(.semibold))
                    .foregroundStyle(methodColor)
                if let status = flow.responseStatus {
                    Text("\(status)")
                        .font(.system(.callout, design: .monospaced).weight(.semibold))
                        .foregroundStyle(statusColor(status))
                }
                Spacer()
            }
            Text(flow.host)
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
            Text(flow.path)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(3)
                .truncationMode(.middle)
        }
    }

    private var detailGrid: some View {
        VStack(alignment: .leading, spacing: 6) {
            metaRow(label: "Type", value: TrafficFilter.resourceKind(for: flow).rawValue)
            metaRow(label: "Size", value: sizeText)
            metaRow(label: "Duration", value: durationText)
            metaRow(label: "Time", value: flow.startedAt.formatted(date: .omitted, time: .standard))
        }
    }

    private func metaRow(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(Theme.textTertiary)
                .tracking(0.6)
                .frame(width: 70, alignment: .leading)
            Text(value)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lineLimit(2)
                .truncationMode(.middle)
        }
    }

    private var sizeText: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(flow.responseBody.count))
    }

    private var durationText: String {
        guard let finished = flow.finishedAt else { return "pending" }
        let interval = finished.timeIntervalSince(flow.startedAt)
        if interval < 1 { return String(format: "%.0f ms", interval * 1000) }
        return String(format: "%.2f s", interval)
    }

    private func headerValue(_ name: String) -> String? {
        flow.responseHeaders.first(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame })?.value
    }

    private var methodColor: Color {
        switch flow.method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        case "CONNECT": return Theme.methodConnect
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
}

// MARK: - Footer hint & count chip

private struct FooterHint: View {
    let symbols: [String]
    let label: String

    var body: some View {
        HStack(spacing: 6) {
            HStack(spacing: 2) {
                ForEach(symbols, id: \.self) { sym in
                    Text(sym)
                        .font(.system(.caption2, design: .monospaced).weight(.semibold))
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 4))
                }
            }
            Text(label)
                .font(.caption)
                .foregroundStyle(Theme.textTertiary)
        }
    }
}

private struct CountChip: View {
    let count: Int

    var body: some View {
        Text("\(count)")
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(Theme.textTertiary)
            .monospacedDigit()
            .contentTransition(.numericText())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.white.opacity(0.05), in: Capsule())
    }
}

// MARK: - Native text field with guaranteed auto-focus

/// AppKit NSTextField wrapped for SwiftUI. Used instead of SwiftUI's
/// TextField + @FocusState because the latter doesn't reliably receive
/// keystrokes when the palette is presented as an overlay on macOS 14 —
/// the responder chain ends up with the wrong first responder and typing
/// goes nowhere. This wrapper grabs first-responder status explicitly the
/// moment the field is attached to the window.
private struct NativeSearchField: NSViewRepresentable {
    @Binding var text: String
    let placeholder: String
    let onSubmit: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSTextField {
        let field = NSTextField()
        field.delegate = context.coordinator
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = .systemFont(ofSize: 18, weight: .regular)
        field.textColor = NSColor(Theme.textPrimary)
        field.placeholderAttributedString = NSAttributedString(
            string: placeholder,
            attributes: [
                .font: NSFont.systemFont(ofSize: 18, weight: .regular),
                .foregroundColor: NSColor(Theme.textTertiary),
            ]
        )
        field.stringValue = text
        field.appearance = NSAppearance(named: .darkAqua)
        field.cell?.usesSingleLineMode = true
        field.cell?.wraps = false
        field.cell?.isScrollable = true

        // Take first responder once the view has a window.
        DispatchQueue.main.async {
            field.window?.makeFirstResponder(field)
            if let editor = field.currentEditor() as? NSTextView {
                editor.insertionPointColor = NSColor(Theme.textPrimary)
            }
        }

        return field
    }

    func updateNSView(_ field: NSTextField, context: Context) {
        context.coordinator.parent = self
        if field.stringValue != text {
            field.stringValue = text
        }
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: NativeSearchField

        init(_ parent: NativeSearchField) {
            self.parent = parent
        }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else { return }
            parent.text = field.stringValue
        }

        func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                parent.onSubmit()
                return true
            }
            return false
        }
    }
}

// MARK: - Visual effect

struct VisualEffect: NSViewRepresentable {
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        view.isEmphasized = true
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
        view.blendingMode = blendingMode
    }
}
