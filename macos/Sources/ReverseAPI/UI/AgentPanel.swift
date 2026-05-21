import SwiftUI
import AppKit
import ReverseAPIProxy

struct AgentPanel: View {
    @Environment(AppState.self) private var state

    var body: some View {
        // No explicit background — both modes inherit Theme.surface from
        // the enclosing Card, which keeps the agent and traffic cards
        // visually matched. Previous `.background(Theme.appBackground)`
        // override made the agent card read darker than the traffic
        // card.
        switch state.agent.mode {
        case .list:
            SessionsListView()
        case .session:
            ActiveSessionView()
        }
    }
}

// MARK: - Active session

private struct ActiveSessionView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var agent = state.agent
        VStack(spacing: 0) {
            SessionHeader(target: $agent.target)
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
    }

    private var flowsToSend: [CapturedFlow] {
        if !state.agentSelection.isEmpty {
            return state.store.flows.filter { state.agentSelection.contains($0.id) }
        }
        return Array(state.store.flows.filter { state.filter.matches($0) }.prefix(100))
    }

    private func send() {
        let flows = flowsToSend
        Task { await state.agent.send(flows: flows) }
    }
}

// MARK: - Session header (minimal: back, language picker)

private struct SessionHeader: View {
    @Environment(AppState.self) private var state
    @Binding var target: AgentTargetLanguage

    var body: some View {
        HStack(spacing: 8) {
            Button {
                state.agent.backToList()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
            }
            .buttonStyle(.plain)
            .help("Back to sessions")
            Spacer()
            LanguageMenu(target: $target)
        }
        .padding(.horizontal, 14)
        .frame(height: 44)
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
                .background(Theme.surface)
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
                .background(Theme.surface)
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
        case .userText(_, let text):
            UserMessageRow(text: text)
        case .assistantText(_, _, let text):
            AssistantRow(text: text)
        case .assistantTextChunk, .sessionStarted:
            // Chunks are folded into the active assistantText event by
            // AgentSession; sessionStarted is metadata only — neither is
            // rendered as a standalone timeline row.
            EmptyView()
        case .toolUse(_, _, let name, let inputJSON):
            ToolUseRow(name: name, inputJSON: inputJSON)
        case .toolResult(_, _, let output, let isError):
            ToolResultRow(output: output, isError: isError)
        case .fileWritten(_, _, let path):
            FileWrittenRow(path: path)
        case .complete(_, _, _, let files):
            // Only surface a completion badge when the agent actually wrote
            // files. For plain Q&A the "Finished · 0 files" pill was noise.
            if !files.isEmpty {
                CompleteRow(fileCount: files.count)
            } else {
                EmptyView()
            }
        case .error(_, _, let message):
            ErrorRow(message: message)
        }
    }
}

private struct UserMessageRow: View {
    let text: String

    var body: some View {
        HStack {
            Spacer(minLength: 40)
            Text(text)
                .font(.body)
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)
                .multilineTextAlignment(.leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 10))
                .fixedSize(horizontal: false, vertical: true)
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
        VStack(alignment: .leading, spacing: 0) {
            Button {
                if !inputJSON.isEmpty { isExpanded.toggle() }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: iconName)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 16)
                    Text(name)
                        .font(.system(.caption, design: .monospaced).weight(.semibold))
                        .foregroundStyle(Theme.textPrimary)
                    if let summary = inlineSummary {
                        Text(summary)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Spacer(minLength: 4)
                    if !inputJSON.isEmpty {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(Theme.textTertiary)
                            .rotationEffect(.degrees(isExpanded ? 90 : 0))
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if isExpanded, !inputJSON.isEmpty {
                Divider().overlay(Theme.border)
                Text(inputJSON)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
        }
    }

    private var iconName: String {
        switch name {
        case "Read": return "doc.text"
        case "Write": return "square.and.pencil"
        case "Edit": return "pencil"
        case "Bash": return "terminal"
        case "Glob", "Grep": return "magnifyingglass"
        default: return "wrench.adjustable"
        }
    }

    /// Pull the most relevant argument out of the tool input JSON so we can
    /// show "Read · flows.json" instead of just the tool name on its own row.
    private var inlineSummary: String? {
        guard !inputJSON.isEmpty,
              let data = inputJSON.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }

        let candidates = ["file_path", "path", "command", "pattern", "url", "query"]
        for key in candidates {
            if let value = obj[key] as? String, !value.isEmpty {
                if key.hasSuffix("path") {
                    return "· " + (value as NSString).lastPathComponent
                }
                return "· " + value
            }
        }
        return nil
    }
}

private struct ToolResultRow: View {
    let output: String
    let isError: Bool
    @State private var isExpanded: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                isExpanded.toggle()
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: isError ? "exclamationmark.octagon" : "checkmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(isError ? Theme.danger : Theme.success)
                        .frame(width: 16)
                    Text(headline)
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Theme.textTertiary)
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if isExpanded {
                Divider().overlay(Theme.border)
                Text(output.isEmpty ? "(empty)" : output)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(isError ? Theme.danger : Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.leading, 24) // align under ToolUseRow's content
    }

    private var headline: String {
        if isError { return "Error" }
        let firstLine = output.split(separator: "\n", omittingEmptySubsequences: true).first.map(String.init) ?? ""
        if firstLine.isEmpty { return "Done" }
        let trimmed = firstLine.trimmingCharacters(in: .whitespaces)
        return trimmed.count > 80 ? String(trimmed.prefix(80)) + "…" : trimmed
    }
}

private struct FileWrittenRow: View {
    @Environment(AppState.self) private var state
    let path: String

    var body: some View {
        Button {
            state.viewFile(at: path)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "doc.text.fill")
                    .foregroundStyle(Theme.success)
                    .font(.caption)
                Text(URL(fileURLWithPath: path).lastPathComponent)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Theme.textTertiary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 7))
        .overlay {
            RoundedRectangle(cornerRadius: 7).stroke(Theme.border, lineWidth: 1)
        }
        .help("View file contents")
        .contextMenu {
            Button("Reveal in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            }
        }
    }
}

private struct CompleteRow: View {
    let fileCount: Int

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(Theme.success)
                .font(.callout)
            Text("Wrote \(fileCount) file\(fileCount == 1 ? "" : "s")")
                .font(.callout)
                .foregroundStyle(Theme.textPrimary)
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
    @Environment(AppState.self) private var state
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
                    let fullPath = (workdir as NSString).appendingPathComponent(file)
                    Button {
                        state.viewFile(at: fullPath)
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "doc")
                                .foregroundStyle(Theme.textTertiary)
                                .font(.caption)
                            Text(file)
                                .font(.system(.callout, design: .monospaced))
                                .foregroundStyle(Theme.textPrimary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(Theme.textTertiary)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 6))
                    .help("View file contents")
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
                    // Cream/dark icon on pink — high contrast, brand-led.
                    .foregroundStyle(canSend ? Color.white : Theme.textTertiary)
                    .frame(width: 28, height: 28)
                    .background(
                        // Brand pink while the user has typed something to
                        // send — the primary action of the entire panel
                        // earns the brand color. Falls back to neutral
                        // `Theme.elevated` when disabled so we don't bait
                        // a click on an empty composer.
                        canSend ? Theme.brandPink : Theme.elevated,
                        in: Circle()
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .help("Send")
        }
        .padding(10)
        .background(Theme.input, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            // 1pt outline so the composer reads as a focused input even
            // before the background lift kicks in — works in both
            // appearances since `Theme.border` is dynamic.
            RoundedRectangle(cornerRadius: 12)
                .stroke(Theme.border, lineWidth: 1)
        )
        .padding(12)
        .background(Theme.surface)
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

        // Word-wrap configuration. By default NSTextView inside NSScrollView
        // assumes a horizontally-growable text container — typed text spills
        // to the right forever instead of wrapping. These properties pin the
        // text container to the scroll view's width so lines break naturally.
        let unbounded = CGFloat.greatestFiniteMagnitude
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: unbounded, height: unbounded)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        if let container = textView.textContainer {
            container.widthTracksTextView = true
            container.containerSize = NSSize(width: 0, height: unbounded)
            container.lineFragmentPadding = 0
        }

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
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
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
