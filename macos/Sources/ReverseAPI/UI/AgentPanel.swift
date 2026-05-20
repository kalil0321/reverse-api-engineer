import SwiftUI
import AppKit
import ReverseAPIProxy

struct AgentPanel: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var agent = state.agent
        VStack(spacing: 0) {
            AgentHeader(target: $agent.target, status: agent.status, onClear: { agent.clear() })
            AgentTimeline(
                events: agent.events,
                flowCount: flowsToSend.count,
                generatedFiles: agent.generatedFiles,
                workdir: agent.lastWorkdir,
                error: agent.lastError,
                status: agent.status
            )
            AgentComposer(input: $agent.input, status: agent.status, onSend: send)
        }
        .background(Theme.appBackground)
    }

    private var flowsToSend: [CapturedFlow] {
        Array(state.store.flows.filter { state.filter.matches($0) }.prefix(100))
    }

    private func send() {
        let flows = flowsToSend
        Task { await state.agent.send(flows: flows) }
    }
}

// MARK: - Header

private struct AgentHeader: View {
    @Binding var target: AgentTargetLanguage
    let status: AgentSession.Status
    let onClear: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(statusColor)
                .frame(width: 7, height: 7)
            VStack(alignment: .leading, spacing: 0) {
                Text("Agent")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(statusLabel)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textTertiary)
            }
            Spacer()
            LanguageMenu(target: $target)
            Button(action: onClear) {
                Image(systemName: "trash")
                    .font(.caption)
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .help("Clear conversation")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var statusColor: Color {
        switch status {
        case .idle: return Theme.textTertiary
        case .launching: return .yellow
        case .ready: return Theme.success
        case .streaming: return Theme.accent
        case .failed: return Theme.danger
        }
    }

    private var statusLabel: String {
        switch status {
        case .idle: return "Idle"
        case .launching: return "Starting…"
        case .ready: return "Ready"
        case .streaming: return "Thinking…"
        case .failed: return "Error"
        }
    }
}

private struct LanguageMenu: View {
    @Binding var target: AgentTargetLanguage

    var body: some View {
        Menu {
            ForEach(AgentTargetLanguage.allCases) { lang in
                Button(lang.displayName) { target = lang }
            }
        } label: {
            HStack(spacing: 4) {
                Text(target.displayName)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Theme.textTertiary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 6))
            .overlay {
                RoundedRectangle(cornerRadius: 6).stroke(Theme.border, lineWidth: 1)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
    }
}

// MARK: - Timeline

private struct AgentTimeline: View {
    let events: [AgentEvent]
    let flowCount: Int
    let generatedFiles: [String]
    let workdir: String?
    let error: String?
    let status: AgentSession.Status

    var body: some View {
        if events.isEmpty && error == nil && generatedFiles.isEmpty && status != .streaming {
            EmptyAgentState()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.appBackground)
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        ForEach(events) { event in
                            AgentEventRow(event: event)
                                .id(event.id)
                        }
                        if status == .streaming {
                            ThinkingRow()
                        }
                        if let error {
                            ErrorRow(message: error)
                        }
                        if !generatedFiles.isEmpty, let workdir {
                            GeneratedFilesRow(workdir: workdir, files: generatedFiles)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 18)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(Theme.appBackground)
                .onChange(of: events.count) { _, _ in
                    if let last = events.last {
                        withAnimation(.easeOut(duration: 0.15)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }
        }
    }
}

private struct EmptyAgentState: View {
    var body: some View {
        Image(systemName: "chevron.left.forwardslash.chevron.right")
            .font(.system(size: 42, weight: .light))
            .foregroundStyle(Theme.textTertiary)
    }
}

// MARK: - Event rows

private struct AgentEventRow: View {
    let event: AgentEvent

    var body: some View {
        switch event {
        case .assistantText(_, _, let text):
            AssistantRow(text: text)
        case .toolUse(_, _, let name, let inputJSON):
            ToolUseRow(name: name, inputJSON: inputJSON)
        case .toolResult(_, _, let output, let isError):
            ToolResultRow(output: output, isError: isError)
        case .fileWritten(_, _, let path):
            FileWrittenRow(path: path)
        case .complete(_, _, let workdir, let files):
            CompleteRow(workdir: workdir, fileCount: files.count)
        case .error(_, _, let message):
            ErrorRow(message: message)
        }
    }
}

private struct AssistantRow: View {
    let text: String

    var body: some View {
        MarkdownView(text: text)
    }
}

private struct ToolUseRow: View {
    let name: String
    let inputJSON: String
    @State private var isExpanded: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                if !inputJSON.isEmpty {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "wrench.adjustable")
                        .font(.caption)
                        .foregroundStyle(Theme.textTertiary)
                    Text(name)
                        .font(.system(.caption, design: .monospaced).weight(.medium))
                        .foregroundStyle(Theme.textSecondary)
                    if !inputJSON.isEmpty {
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(Theme.textTertiary)
                    }
                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isExpanded, !inputJSON.isEmpty {
                Text(inputJSON)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.appBackground, in: RoundedRectangle(cornerRadius: 6))
                    .overlay {
                        RoundedRectangle(cornerRadius: 6).stroke(Theme.border, lineWidth: 1)
                    }
            }
        }
    }
}

private struct ToolResultRow: View {
    let output: String
    let isError: Bool
    @State private var isExpanded: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                isExpanded.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: isError ? "xmark.circle" : "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(isError ? Theme.danger : Theme.textTertiary)
                    Text(isError ? "result · error" : "result")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(Theme.textTertiary)
                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isExpanded {
                Text(output)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(isError ? Theme.danger : Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.appBackground, in: RoundedRectangle(cornerRadius: 6))
                    .overlay {
                        RoundedRectangle(cornerRadius: 6).stroke(Theme.border, lineWidth: 1)
                    }
            }
        }
    }
}

private struct FileWrittenRow: View {
    let path: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "doc.text.fill")
                .foregroundStyle(Theme.success)
                .font(.caption)
            Text(URL(fileURLWithPath: path).lastPathComponent)
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            } label: {
                Image(systemName: "arrow.up.right.square")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
            .buttonStyle(.plain)
            .help("Reveal in Finder")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 7))
        .overlay {
            RoundedRectangle(cornerRadius: 7).stroke(Theme.border, lineWidth: 1)
        }
    }
}

private struct CompleteRow: View {
    let workdir: String
    let fileCount: Int

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(Theme.success)
                .font(.callout)
            Text("Finished · \(fileCount) file\(fileCount == 1 ? "" : "s")")
                .font(.callout)
                .foregroundStyle(Theme.textPrimary)
            Text(URL(fileURLWithPath: workdir).lastPathComponent)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(Theme.textTertiary)
            Spacer()
        }
    }
}

private struct ErrorRow: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.danger)
                .font(.callout)
            Text(message)
                .font(.callout)
                .foregroundStyle(Theme.danger)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.danger.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).stroke(Theme.danger.opacity(0.25), lineWidth: 1)
        }
    }
}

private struct ThinkingRow: View {
    @State private var phase: Int = 0
    private let timer = Timer.publish(every: 0.45, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<3) { i in
                Circle()
                    .fill(Theme.textSecondary)
                    .frame(width: 5, height: 5)
                    .opacity(phase == i ? 1 : 0.3)
            }
        }
        .onReceive(timer) { _ in
            phase = (phase + 1) % 3
        }
    }
}

private struct GeneratedFilesRow: View {
    let workdir: String
    let files: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("GENERATED FILES")
                    .font(.system(size: 10, weight: .semibold, design: .default))
                    .foregroundStyle(Theme.textTertiary)
                    .tracking(0.8)
                Spacer()
                Button {
                    NSWorkspace.shared.open(URL(fileURLWithPath: workdir))
                } label: {
                    Text("Open folder")
                        .font(.caption)
                        .foregroundStyle(Theme.accent)
                }
                .buttonStyle(.plain)
            }
            VStack(alignment: .leading, spacing: 4) {
                ForEach(files, id: \.self) { file in
                    HStack(spacing: 8) {
                        Image(systemName: "doc")
                            .foregroundStyle(Theme.textTertiary)
                            .font(.caption)
                        Text(file)
                            .font(.system(.callout, design: .monospaced))
                            .foregroundStyle(Theme.textPrimary)
                            .textSelection(.enabled)
                        Spacer()
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 6))
                }
            }
        }
        .padding(.top, 4)
    }
}

// MARK: - Composer

private struct AgentComposer: View {
    @Binding var input: String
    let status: AgentSession.Status
    let onSend: () -> Void

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            ZStack(alignment: .topLeading) {
                if input.isEmpty {
                    Text("Ask the agent…")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textTertiary)
                        .padding(.leading, 5)
                        .padding(.top, 4)
                        .allowsHitTesting(false)
                }
                NativeMultilineTextField(text: $input, onSubmit: {
                    if canSend { onSend() }
                })
                .frame(minHeight: 22, maxHeight: 120)
            }

            Button(action: { if canSend { onSend() } }) {
                Image(systemName: "arrow.up")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(canSend ? Theme.appBackground : Theme.textTertiary)
                    .frame(width: 28, height: 28)
                    .background(
                        canSend ? Theme.textPrimary : Theme.elevated,
                        in: Circle()
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .help("Send")
        }
        .padding(10)
        .background(Theme.input, in: RoundedRectangle(cornerRadius: 12))
        .padding(12)
        .background(Theme.appBackground)
    }

    private var canSend: Bool {
        guard !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        return status != .launching
    }
}

/// Multi-line NSTextView wrapped for SwiftUI. Avoids the broken SwiftUI
/// TextField(axis: .vertical) + .focused() + ZStack overlay combination,
/// which on macOS 14 fails to receive key events in certain hosting
/// configurations. Returns Enter to submit, Shift+Enter to insert a newline.
private struct NativeMultilineTextField: NSViewRepresentable {
    @Binding var text: String
    let onSubmit: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let textView = NSTextView()
        textView.delegate = context.coordinator
        textView.isRichText = false
        textView.isEditable = true
        textView.isSelectable = true
        textView.allowsUndo = true

        // Force every color path explicitly. NSTextView renders typed
        // characters using `typingAttributes`, NOT `textColor` alone, and
        // when `textColor` resolves through `.labelColor` against an
        // unflushed appearance the result is sometimes the same near-black
        // as the composer background — invisible text. Hard-code white
        // so the text is always legible against `Theme.input`.
        let font = NSFont.systemFont(ofSize: 13)
        let typingColor = NSColor.white
        textView.font = font
        textView.textColor = typingColor
        textView.insertionPointColor = typingColor
        textView.typingAttributes = [
            .foregroundColor: typingColor,
            .font: font,
        ]
        textView.selectedTextAttributes = [
            .backgroundColor: NSColor.selectedTextBackgroundColor,
            .foregroundColor: typingColor,
        ]
        textView.drawsBackground = false
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 1, height: 4)
        textView.appearance = NSAppearance(named: .darkAqua)
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticSpellingCorrectionEnabled = false
        textView.isAutomaticTextCompletionEnabled = false
        textView.isAutomaticLinkDetectionEnabled = false
        textView.isAutomaticDataDetectionEnabled = false

        let scroll = NSScrollView()
        scroll.documentView = textView
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = false
        scroll.hasHorizontalScroller = false
        scroll.borderType = .noBorder
        scroll.appearance = NSAppearance(named: .darkAqua)

        context.coordinator.textView = textView
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let textView = scroll.documentView as? NSTextView else { return }
        context.coordinator.parent = self
        if textView.string != text {
            textView.string = text
            // Setting `.string` strips attributes; re-apply our font/color
            // to the whole range so the existing text stays visible too.
            let attributes: [NSAttributedString.Key: Any] = [
                .foregroundColor: NSColor.white,
                .font: NSFont.systemFont(ofSize: 13),
            ]
            textView.textStorage?.setAttributes(
                attributes,
                range: NSRange(location: 0, length: textView.string.utf16.count)
            )
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: NativeMultilineTextField
        weak var textView: NSTextView?

        init(_ parent: NativeMultilineTextField) {
            self.parent = parent
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            parent.text = textView.string
        }

        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                let shift = NSApp.currentEvent?.modifierFlags.contains(.shift) ?? false
                if shift {
                    textView.insertNewlineIgnoringFieldEditor(nil)
                } else {
                    parent.onSubmit()
                }
                return true
            }
            return false
        }
    }
}
