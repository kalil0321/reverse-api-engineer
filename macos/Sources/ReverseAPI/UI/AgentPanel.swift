import SwiftUI
import AppKit
import ReverseAPIProxy

struct AgentPanel: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var agent = state.agent
        VStack(spacing: 0) {
            AgentHeader(target: $agent.target, status: agent.status, onClear: { agent.clear() })
            Divider()
            AgentTimeline(events: agent.events, flowCount: flowsToSend.count, generatedFiles: agent.generatedFiles, workdir: agent.lastWorkdir, status: agent.status, error: agent.lastError)
            Divider()
            AgentComposer(input: $agent.input, status: agent.status, onSend: send)
        }
        .frame(minWidth: 360)
    }

    private var flowsToSend: [CapturedFlow] {
        Array(state.store.flows.filter { state.filter.matches($0) }.prefix(100))
    }

    private func send() {
        let flows = flowsToSend
        Task { await state.agent.send(flows: flows) }
    }
}

private struct AgentHeader: View {
    @Binding var target: AgentTargetLanguage
    let status: AgentSession.Status
    let onClear: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                statusDot
                Text(statusLabel)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Picker("", selection: $target) {
                ForEach(AgentTargetLanguage.allCases) { lang in
                    Text(lang.displayName).tag(lang)
                }
            }
            .pickerStyle(.menu)
            .fixedSize()
            Button(action: onClear) {
                Image(systemName: "eraser.line.dashed")
            }
            .buttonStyle(.borderless)
            .help("Clear conversation")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private var statusDot: some View {
        Circle()
            .fill(statusColor)
            .frame(width: 8, height: 8)
    }

    private var statusColor: Color {
        switch status {
        case .idle: return .secondary
        case .launching: return .yellow
        case .ready: return .green
        case .streaming: return .blue
        case .failed: return .red
        }
    }

    private var statusLabel: String {
        switch status {
        case .idle: return "Agent: idle"
        case .launching: return "Agent: starting"
        case .ready: return "Agent: ready"
        case .streaming: return "Agent: thinking"
        case .failed: return "Agent: error"
        }
    }
}

private struct AgentTimeline: View {
    let events: [AgentEvent]
    let flowCount: Int
    let generatedFiles: [String]
    let workdir: String?
    let status: AgentSession.Status
    let error: String?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    introCard
                    ForEach(events) { event in
                        AgentEventRow(event: event)
                            .id(event.id)
                    }
                    if let error {
                        ErrorBubble(message: error)
                    }
                    if !generatedFiles.isEmpty, let workdir {
                        GeneratedFilesCard(workdir: workdir, files: generatedFiles)
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: events.count) { _, _ in
                if let last = events.last {
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
    }

    private var introCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Reverse engineer with the agent")
                .font(.headline)
            Text("The agent will see the filtered flows (currently \(flowCount)) and generate an API client. Files land in the session workdir.")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct AgentEventRow: View {
    let event: AgentEvent

    var body: some View {
        switch event {
        case .assistantText(_, _, let text):
            AssistantBubble(text: text)
        case .toolUse(_, _, let name, let inputJSON):
            ToolUseBubble(name: name, inputJSON: inputJSON)
        case .toolResult(_, _, let output, let isError):
            ToolResultBubble(output: output, isError: isError)
        case .fileWritten(_, _, let path):
            FileWrittenBubble(path: path)
        case .complete(_, _, let workdir, let files):
            CompleteBubble(workdir: workdir, fileCount: files.count)
        case .error(_, _, let message):
            ErrorBubble(message: message)
        }
    }
}

private struct AssistantBubble: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.body)
            .textSelection(.enabled)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct ToolUseBubble: View {
    let name: String
    let inputJSON: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "wrench.and.screwdriver")
                    .foregroundStyle(.tint)
                Text(name)
                    .font(.system(.callout, design: .monospaced).weight(.semibold))
            }
            if !inputJSON.isEmpty {
                Text(inputJSON)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(8)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct ToolResultBubble: View {
    let output: String
    let isError: Bool

    var body: some View {
        Text(output)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(isError ? .red : .secondary)
            .textSelection(.enabled)
            .lineLimit(10)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background((isError ? Color.red : Color.gray).opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct FileWrittenBubble: View {
    let path: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "doc.badge.plus")
                .foregroundStyle(.green)
            Text(URL(fileURLWithPath: path).lastPathComponent)
                .font(.system(.callout, design: .monospaced))
            Spacer()
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            } label: {
                Image(systemName: "arrow.up.right.square")
            }
            .buttonStyle(.borderless)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct CompleteBubble: View {
    let workdir: String
    let fileCount: Int

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(.green)
            Text("Agent finished — \(fileCount) file\(fileCount == 1 ? "" : "s") at \(URL(fileURLWithPath: workdir).lastPathComponent)")
                .font(.callout)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct ErrorBubble: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.octagon.fill")
                .foregroundStyle(.red)
            Text(message)
                .font(.callout)
                .textSelection(.enabled)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct GeneratedFilesCard: View {
    let workdir: String
    let files: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Generated files")
                    .font(.headline)
                Spacer()
                Button("Open in Finder") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: workdir))
                }
                .buttonStyle(.borderless)
            }
            ForEach(files, id: \.self) { file in
                HStack {
                    Image(systemName: "doc")
                        .foregroundStyle(.secondary)
                    Text(file)
                        .font(.system(.callout, design: .monospaced))
                        .textSelection(.enabled)
                    Spacer()
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct AgentComposer: View {
    @Binding var input: String
    let status: AgentSession.Status
    let onSend: () -> Void

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask the agent…", text: $input, axis: .vertical)
                .lineLimit(1...6)
                .textFieldStyle(.roundedBorder)
                .onSubmit(onSend)
            Button(action: onSend) {
                Image(systemName: "paperplane.fill")
                    .frame(width: 22, height: 22)
            }
            .buttonStyle(.borderedProminent)
            .keyboardShortcut(.return, modifiers: [.command])
            .disabled(!canSend)
        }
        .padding(14)
        .background(.bar)
    }

    private var canSend: Bool {
        guard !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        return status != .launching
    }
}
