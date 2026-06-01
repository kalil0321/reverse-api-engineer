import SwiftUI
import AppKit

/// Sheet that pops over the window when the user taps a file the agent
/// wrote. Reads the file lazily, shows it monospaced with line numbers
/// against `Theme.appBackground`, and adapts the chrome (language label,
/// byte count) so it reads a bit like a diff viewer / GitHub blob preview.
struct AgentFileViewer: View {
    let url: URL
    @Binding var isPresented: Bool

    @State private var content: String = ""
    @State private var loadError: String?
    @State private var isLoading: Bool = true

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Theme.border)
            body(content)
        }
        .frame(minWidth: 720, idealWidth: 880, minHeight: 480, idealHeight: 640)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.border, lineWidth: 1)
        }
        .task(id: url) { await load() }
    }

    // MARK: - Subviews

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: iconForExtension)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(url.lastPathComponent)
                    .font(.system(.body, design: .monospaced).weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let metadata {
                    Text(metadata)
                        .font(.caption)
                        .foregroundStyle(Theme.textTertiary)
                }
            }
            Spacer()
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } label: {
                Image(systemName: "arrow.up.right.square")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .help("Reveal in Finder")

            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(content, forType: .string)
            } label: {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .help("Copy contents")
            .disabled(content.isEmpty)

            Button {
                isPresented = false
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .help("Close")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    @ViewBuilder
    private func body(_ content: String) -> some View {
        if isLoading {
            VStack {
                ProgressView()
                    .controlSize(.small)
                    .tint(Theme.textSecondary)
                Spacer()
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 40)
        } else if let loadError {
            VStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 24, weight: .light))
                    .foregroundStyle(Theme.danger)
                Text("Couldn't open file")
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text(loadError)
                    .font(.callout)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(20)
        } else {
            ScrollView([.vertical, .horizontal]) {
                HStack(alignment: .top, spacing: 0) {
                    LineGutter(lineCount: lineCount(content))
                    Text(content)
                        .font(.system(size: 12.5, weight: .regular, design: .monospaced))
                        .foregroundStyle(Theme.textPrimary)
                        .textSelection(.enabled)
                        .lineSpacing(2)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .background(Theme.appBackground)
        }
    }

    // MARK: - Loading

    private func load() async {
        isLoading = true
        loadError = nil
        let url = self.url
        do {
            let text = try await Task.detached(priority: .userInitiated) { () -> String in
                let data = try Data(contentsOf: url)
                if let utf8 = String(data: data, encoding: .utf8) { return utf8 }
                return "<binary file · \(data.count) bytes>"
            }.value
            content = text
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }

    private func lineCount(_ text: String) -> Int {
        if text.isEmpty { return 1 }
        var count = 0
        for char in text where char == "\n" { count += 1 }
        if text.last != "\n" { count += 1 }
        return count
    }

    // MARK: - Metadata

    private var metadata: String? {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path) else { return nil }
        let size = (attrs[.size] as? NSNumber)?.int64Value ?? 0
        let bytes = ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
        let language = languageLabel
        if let language { return "\(language) · \(bytes)" }
        return bytes
    }

    private var languageLabel: String? {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "py": return "Python"
        case "ts", "tsx": return "TypeScript"
        case "js", "mjs": return "JavaScript"
        case "go": return "Go"
        case "swift": return "Swift"
        case "json": return "JSON"
        case "md", "markdown": return "Markdown"
        case "html", "htm": return "HTML"
        case "css": return "CSS"
        case "yaml", "yml": return "YAML"
        case "toml": return "TOML"
        case "sh", "bash", "zsh": return "Shell"
        case "rb": return "Ruby"
        case "rs": return "Rust"
        case "java": return "Java"
        case "kt": return "Kotlin"
        case "": return nil
        default: return ext.uppercased()
        }
    }

    private var iconForExtension: String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "py", "ts", "tsx", "js", "mjs", "go", "swift", "rs", "rb", "java", "kt":
            return "curlybraces"
        case "json", "yaml", "yml", "toml":
            return "doc.text"
        case "md", "markdown":
            return "doc.richtext"
        case "html", "htm", "css":
            return "globe"
        case "sh", "bash", "zsh":
            return "terminal"
        default:
            return "doc"
        }
    }
}

private struct LineGutter: View {
    let lineCount: Int

    var body: some View {
        VStack(alignment: .trailing, spacing: 0) {
            ForEach(1...max(1, lineCount), id: \.self) { line in
                Text("\(line)")
                    .font(.system(size: 11.5, weight: .regular, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
                    .lineSpacing(2)
                    .frame(minWidth: 32, alignment: .trailing)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 12)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.surface)
        .overlay(alignment: .trailing) {
            Rectangle().fill(Theme.border).frame(width: 1)
        }
    }
}
