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
    @State private var isSettingsVisible = false

    var body: some View {
        @Bindable var agent = state.agent
        VStack(spacing: 0) {
            SessionHeader(target: $agent.target, isSettingsVisible: $isSettingsVisible)
            AgentTimeline(
                events: agent.events,
                flowCount: flowsToSend.count,
                generatedFiles: agent.generatedFiles,
                workdir: agent.lastWorkdir,
                error: agent.lastError,
                status: agent.status
            )
            AgentComposer(agent: agent, input: $agent.input, status: agent.status, onSend: send)
        }
        .sheet(isPresented: $isSettingsVisible) {
            AgentSettingsView(agent: state.agent, isPresented: $isSettingsVisible)
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
    @Binding var isSettingsVisible: Bool

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
            Button {
                isSettingsVisible = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
            }
            .buttonStyle(.plain)
            .help("Settings — model, usage, cost")
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
                    // 12pt between adjacent timeline rows — was 18 which
                    // left visible gaps after the new minimal V4 narrative
                    // tool-call lines (which barely have any internal
                    // padding of their own). 12 keeps rows distinct
                    // without feeling sparse.
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(groupedEvents) { group in
                            timelineGroup(group)
                                .id(group.id)
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

    /// Pair adjacent `toolUse` + `toolResult` events so the renderer can
    /// display them in a single unified `ToolCallView` card instead of
    /// two visually disconnected rows. Unpaired `toolUse` (still
    /// in-flight, no result yet) renders with a running indicator;
    /// unpaired `toolResult` (shouldn't normally happen) falls through
    /// as a standalone row.
    private var groupedEvents: [TimelineGroup] {
        var groups: [TimelineGroup] = []
        var i = 0
        while i < events.count {
            let event = events[i]
            if case .toolUse(_, let useID, let name, let inputJSON) = event {
                if i + 1 < events.count,
                   case .toolResult(_, _, let output, let isError) = events[i + 1] {
                    groups.append(.toolPair(
                        id: useID,
                        name: name,
                        inputJSON: inputJSON,
                        result: .init(output: output, isError: isError)
                    ))
                    i += 2
                    continue
                }
                groups.append(.toolPair(
                    id: useID,
                    name: name,
                    inputJSON: inputJSON,
                    result: nil
                ))
                i += 1
                continue
            }
            groups.append(.single(event))
            i += 1
        }
        return groups
    }

    @ViewBuilder
    private func timelineGroup(_ group: TimelineGroup) -> some View {
        switch group {
        case .single(let event):
            AgentEventRow(event: event)
        case .toolPair(_, let name, let inputJSON, let result):
            ToolCallView(name: name, inputJSON: inputJSON, result: result)
        }
    }
}

/// Either a standalone timeline event or a tool-call/result pair that
/// should render as one unified card.
private enum TimelineGroup: Identifiable {
    case single(AgentEvent)
    case toolPair(id: UUID, name: String, inputJSON: String, result: ToolCallView.ToolResult?)

    var id: AnyHashable {
        switch self {
        case .single(let event): return AnyHashable(event.id)
        case .toolPair(let id, _, _, _): return AnyHashable(id)
        }
    }
}

private struct EmptyAgentState: View {
    var body: some View {
        Text("*")
            .font(.fraunces(size: 56, weight: 400))
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
        case .assistantTextChunk, .sessionStarted, .usage, .cancelled:
            // Chunks are folded into the active assistantText event;
            // sessionStarted / usage / cancelled are metadata only —
            // not rendered as standalone timeline rows.
            EmptyView()
        case .toolUse(_, _, let name, let inputJSON):
            // Normally folded into the preceding `toolPair` group; this
            // path only fires if the timeline ordering breaks (a tool_use
            // without a matching tool_result reaching the group pass).
            // Render the unified card with no result so the user still
            // sees what the agent tried to invoke.
            ToolCallView(name: name, inputJSON: inputJSON, result: nil)
        case .toolResult:
            // Same story — should already be paired with its tool_use at
            // the group level. If we get here standalone, suppress: a
            // bare result without context is just noise.
            EmptyView()
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

/// Unified tool-call card — renders a tool's invocation AND its result
/// inside a single rounded container. The two sections share the same
/// border, the same expand toggle, and are split only by a thin internal
/// divider so the eye reads them as one logical unit instead of two
/// disconnected rows.
///
/// The `result` is optional because `tool_use` events stream in before
/// the matching `tool_result` lands. When `result == nil` we show a
/// "running" indicator in the header. Once the matching result arrives,
/// the timeline regroups events and re-renders this card with the
/// populated result section.
/// V4 Cursor-narrative tool-call card (picked from the DesignLab pass).
/// One line of plain prose summarising what the agent just did
/// (`"Read flows.json"`, `"Ran a shell command to extract GraphQL
/// shapes"`, …) with an eye button on the right to peek at the raw
/// result body. While the tool is still in-flight (no result event
/// yet), the eye is replaced by a running spinner.
///
/// Why this style: tool calls are signal, not chrome. The agent's
/// reasoning reads like a normal conversation; tool actions slot into
/// that conversation as one-liners that don't demand visual real
/// estate unless the user explicitly asks to see the raw bytes.
struct ToolCallView: View {
    let name: String
    let inputJSON: String
    let result: ToolResult?
    @State private var isPeeking: Bool = false

    struct ToolResult {
        let output: String
        let isError: Bool
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: iconName)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 14, alignment: .center)
                Text(narrative)
                    .font(.callout)
                    .foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                trailingControl
            }
            if isPeeking, let result, !result.output.isEmpty {
                Text(result.output)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(result.isError ? Theme.danger : Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.elevated.opacity(0.6), in: RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
                    )
                    .padding(.leading, 22)
            }
        }
    }

    @ViewBuilder
    private var trailingControl: some View {
        if result == nil {
            ProgressView()
                .controlSize(.small)
                .scaleEffect(0.7)
                .frame(width: 22, height: 22)
        } else if let result, !result.output.isEmpty {
            Button { isPeeking.toggle() } label: {
                Image(systemName: isPeeking ? "eye.slash" : "eye")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
            }
            .buttonStyle(.plain)
            .help(isPeeking ? "Hide output" : "Show output")
        } else if let result {
            Image(systemName: result.isError ? "exclamationmark.octagon.fill" : "checkmark")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(result.isError ? Theme.danger : Theme.success)
                .frame(width: 22, height: 22)
        }
    }

    // MARK: - Narrative generation

    /// One-line natural-language summary of the call. Prefers the tool's
    /// `description` argument when present (Bash + agent-friendly tools
    /// populate it with intent like "Extract GraphQL shapes"). Falls
    /// back to tool-specific arg extraction (file_path, command, …) so
    /// even a description-less call still reads as something a human
    /// would say.
    private var narrative: String {
        let parsed = parsedInput
        let suffix = resultSuffix

        if let desc = parsed["description"] as? String, !desc.isEmpty {
            switch name {
            case "Bash":
                let lowered = desc.first.map { String($0).lowercased() + desc.dropFirst() } ?? desc
                return "Ran a shell command to \(lowered)\(suffix)"
            default:
                return "\(name) — \(desc)\(suffix)"
            }
        }

        switch name {
        case "Read":
            if let path = parsed["file_path"] as? String ?? parsed["path"] as? String {
                return "Read \(filename(path))\(suffix)"
            }
            return "Read a file\(suffix)"
        case "Write":
            if let path = parsed["file_path"] as? String ?? parsed["path"] as? String {
                return "Wrote \(filename(path))\(suffix)"
            }
            return "Wrote a file\(suffix)"
        case "Edit":
            if let path = parsed["file_path"] as? String ?? parsed["path"] as? String {
                return "Edited \(filename(path))\(suffix)"
            }
            return "Edited a file\(suffix)"
        case "Bash":
            if let cmd = parsed["command"] as? String, !cmd.isEmpty {
                let short = cmd.count > 60
                    ? String(cmd.prefix(57)) + "…"
                    : cmd
                return "Ran \(short)\(suffix)"
            }
            return "Ran a shell command\(suffix)"
        case "Glob":
            if let pattern = parsed["pattern"] as? String {
                return "Searched for files matching \(pattern)\(suffix)"
            }
            return "Searched the filesystem\(suffix)"
        case "Grep":
            if let pattern = parsed["pattern"] as? String {
                return "Grepped for \(pattern)\(suffix)"
            }
            return "Grepped for a pattern\(suffix)"
        default:
            return "\(name) call\(suffix)"
        }
    }

    /// Trailing summary about the result: " — N lines", " — error",
    /// "" (silent on empty success), or "…" while still in flight.
    private var resultSuffix: String {
        guard let result else { return "…" }
        if result.isError { return " — error" }
        if result.output.isEmpty { return "" }
        let lines = result.output.split(separator: "\n", omittingEmptySubsequences: false).count
        return lines == 1 ? " — 1 line of output" : " — \(lines) lines of output"
    }

    private var parsedInput: [String: Any] {
        guard !inputJSON.isEmpty,
              let data = inputJSON.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [:] }
        return obj
    }

    private func filename(_ path: String) -> String {
        (path as NSString).lastPathComponent
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
}

/// Small "copy to clipboard" affordance used inside expanded tool-call /
/// tool-result panels. Flashes a checkmark for 1.2s after a copy so the
/// user gets feedback without a noisy toast.
private struct InlineCopyButton: View {
    let text: String
    @State private var didCopy = false

    var body: some View {
        Button {
            let pb = NSPasteboard.general
            pb.clearContents()
            pb.setString(text, forType: .string)
            withAnimation(.easeInOut(duration: 0.18)) { didCopy = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                withAnimation(.easeInOut(duration: 0.18)) { didCopy = false }
            }
        } label: {
            Image(systemName: didCopy ? "checkmark" : "doc.on.doc")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(didCopy ? Theme.success : Theme.textTertiary)
                .frame(width: 22, height: 22)
                .background(Theme.elevated, in: RoundedRectangle(cornerRadius: 5))
                .overlay(
                    RoundedRectangle(cornerRadius: 5).stroke(Theme.border, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .help(didCopy ? "Copied" : "Copy to clipboard")
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
    @State private var start = Date()

    var body: some View {
        TimelineView(.animation) { context in
            let elapsed = context.date.timeIntervalSince(start)
            let cycle: Double = 2.6
            let phase = elapsed.truncatingRemainder(dividingBy: cycle) / cycle
            // -0.5..1.5 so the band enters / exits off-screen rather
            // than appearing abruptly at the edges.
            let center = phase * 2.0 - 0.5
            Text("thinking…")
                .font(.callout.weight(.medium))
                .foregroundStyle(
                    LinearGradient(
                        stops: [
                            .init(color: Theme.textSecondary, location: 0),
                            .init(color: Theme.textSecondary, location: max(0, center - 0.35)),
                            .init(color: Theme.textPrimary, location: max(0, min(1, center - 0.1))),
                            .init(color: Theme.brandPink, location: max(0, min(1, center))),
                            .init(color: Theme.textPrimary, location: min(1, center + 0.1)),
                            .init(color: Theme.textSecondary, location: min(1, center + 0.35)),
                            .init(color: Theme.textSecondary, location: 1),
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
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
    @Bindable var agent: AgentSession
    @Binding var input: String
    let status: AgentSession.Status
    let onSend: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
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
            HStack(alignment: .center, spacing: 8) {
                ModelPickerPill(agent: agent)
                Spacer(minLength: 0)
                if status == .streaming {
                    Button { Task { await agent.cancel() } } label: {
                        Image(systemName: "stop.fill")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(Color.white)
                            .frame(width: 26, height: 26)
                            .background(Theme.brandPink, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .help("Stop generating")
                } else {
                    Button(action: { if canSend { onSend() } }) {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(canSend ? Color.white : Theme.textTertiary)
                            .frame(width: 26, height: 26)
                            .background(
                                canSend ? Theme.brandPink : Theme.elevated,
                                in: Circle()
                            )
                    }
                    .buttonStyle(.plain)
                    .disabled(!canSend)
                    .help("Send")
                }
            }
        }
        .padding(10)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Theme.borderStrong, lineWidth: 1)
        )
        .padding(12)
        .background(Theme.surface)
    }

    private var canSend: Bool {
        guard !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        return status != .launching
    }
}

struct ModelPickerPill: View {
    @Bindable var agent: AgentSession

    private static let presets: [(id: String, label: String)] = [
        ("claude-opus-4-7", "Opus 4.7"),
        ("claude-sonnet-4-6", "Sonnet 4.6"),
        ("claude-haiku-4-5-20251001", "Haiku 4.5"),
    ]

    @State private var showingCustomSheet = false
    @State private var customModel: String = ""

    var body: some View {
        Menu {
            ForEach(Self.presets, id: \.id) { preset in
                Button {
                    agent.selectedModel = preset.id
                } label: {
                    HStack {
                        Text(preset.label)
                        Spacer()
                        if agent.selectedModel == preset.id { Image(systemName: "checkmark") }
                    }
                }
            }
            Divider()
            Button {
                customModel = isCustom ? agent.selectedModel : ""
                showingCustomSheet = true
            } label: {
                HStack {
                    Text("Custom model ID…")
                    Spacer()
                    if isCustom { Image(systemName: "checkmark") }
                }
            }
        } label: {
            HStack(spacing: 6) {
                ClaudeMark(size: 12)
                Text(displayLabel)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Color.white)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(Color.white.opacity(0.55))
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(Theme.brandPink.opacity(0.10), in: Capsule())
            .overlay(Capsule().stroke(Theme.brandPink.opacity(0.35), lineWidth: 1))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .sheet(isPresented: $showingCustomSheet) {
            CustomModelSheet(
                current: $customModel,
                isPresented: $showingCustomSheet,
                onApply: { value in
                    let trimmed = value.trimmingCharacters(in: .whitespaces)
                    if !trimmed.isEmpty {
                        agent.selectedModel = trimmed
                    }
                }
            )
        }
    }

    private var displayLabel: String {
        Self.presets.first(where: { $0.id == agent.selectedModel })?.label ?? agent.selectedModel
    }

    private var isCustom: Bool {
        !Self.presets.contains(where: { $0.id == agent.selectedModel })
    }
}

private struct CustomModelSheet: View {
    @Binding var current: String
    @Binding var isPresented: Bool
    let onApply: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Custom model ID")
                .font(.fraunces(size: 18, weight: 400))
                .foregroundStyle(Theme.textPrimary)
            Text("Any model id the Anthropic API recognises — e.g. `claude-3-5-sonnet-20241022`.")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
            TextField("claude-3-5-sonnet-20241022", text: $current)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(Theme.appBackground, in: RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6).stroke(Theme.border, lineWidth: 1)
                )
            HStack {
                Spacer()
                Button("Cancel") { isPresented = false }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.textSecondary)
                Button("Apply") {
                    onApply(current)
                    isPresented = false
                }
                .buttonStyle(.plain)
                .font(.callout.weight(.semibold))
                .foregroundStyle(Theme.brandPink)
                .disabled(current.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(24)
        .frame(width: 420)
        .background(Theme.surface)
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
