import SwiftUI

/// Lightweight markdown renderer for assistant output.
/// Supports: fenced code blocks, headers, bullet/ordered lists, paragraphs.
/// Inline syntax (bold/italic/code/links) is handled by AttributedString.
struct MarkdownView: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                view(for: block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var blocks: [MarkdownBlock] {
        MarkdownParser.parse(text)
    }

    @ViewBuilder
    private func view(for block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let raw):
            Text(inline(raw))
                .font(headingFont(level: level))
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)
                .padding(.top, level == 1 ? 4 : 2)

        case .paragraph(let raw):
            Text(inline(raw))
                .font(.body)
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

        case .bullet(let items):
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("•")
                            .foregroundStyle(Theme.textSecondary)
                        Text(inline(item))
                            .font(.body)
                            .foregroundStyle(Theme.textPrimary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

        case .ordered(let items):
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\(index + 1).")
                            .foregroundStyle(Theme.textSecondary)
                            .monospacedDigit()
                        Text(inline(item))
                            .font(.body)
                            .foregroundStyle(Theme.textPrimary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

        case .codeBlock(let language, let code):
            MarkdownCodeBlock(language: language, code: code)
        }
    }

    private func inline(_ raw: String) -> AttributedString {
        if let attr = try? AttributedString(markdown: raw, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return attr
        }
        return AttributedString(raw)
    }

    private func headingFont(level: Int) -> Font {
        switch level {
        case 1: return .system(.title2, design: .default).weight(.semibold)
        case 2: return .system(.title3, design: .default).weight(.semibold)
        default: return .system(.headline, design: .default)
        }
    }
}

private struct MarkdownCodeBlock: View {
    let language: String?
    let code: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let language, !language.isEmpty {
                HStack {
                    Text(language)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(Theme.textTertiary)
                        .textCase(.lowercase)
                    Spacer()
                    Button {
                        let pb = NSPasteboard.general
                        pb.clearContents()
                        pb.setString(code, forType: .string)
                    } label: {
                        Image(systemName: "doc.on.doc")
                            .font(.caption2)
                            .foregroundStyle(Theme.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .help("Copy")
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Theme.elevated)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.appBackground)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
        }
    }
}

// MARK: - Parser

enum MarkdownBlock: Equatable {
    case heading(level: Int, text: String)
    case paragraph(String)
    case bullet([String])
    case ordered([String])
    case codeBlock(language: String?, code: String)
}

enum MarkdownParser {
    static func parse(_ text: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var lines = text.components(separatedBy: "\n")[...]

        var paragraphBuffer: [String] = []
        var bulletBuffer: [String] = []
        var orderedBuffer: [String] = []

        func flushParagraph() {
            if !paragraphBuffer.isEmpty {
                blocks.append(.paragraph(paragraphBuffer.joined(separator: " ")))
                paragraphBuffer.removeAll()
            }
        }
        func flushBullets() {
            if !bulletBuffer.isEmpty {
                blocks.append(.bullet(bulletBuffer))
                bulletBuffer.removeAll()
            }
        }
        func flushOrdered() {
            if !orderedBuffer.isEmpty {
                blocks.append(.ordered(orderedBuffer))
                orderedBuffer.removeAll()
            }
        }
        func flushAll() {
            flushParagraph()
            flushBullets()
            flushOrdered()
        }

        while let line = lines.first {
            lines = lines.dropFirst()

            // Fenced code block
            if let fence = codeFence(line) {
                flushAll()
                var collected: [String] = []
                while let next = lines.first {
                    lines = lines.dropFirst()
                    if codeFence(next) != nil { break }
                    collected.append(next)
                }
                blocks.append(.codeBlock(language: fence, code: collected.joined(separator: "\n")))
                continue
            }

            let trimmed = line.trimmingCharacters(in: .whitespaces)

            // Blank line ⇒ flush paragraph
            if trimmed.isEmpty {
                flushAll()
                continue
            }

            // Heading
            if let (level, rest) = headingMatch(trimmed) {
                flushAll()
                blocks.append(.heading(level: level, text: rest))
                continue
            }

            // Bullet
            if let item = bulletMatch(trimmed) {
                flushParagraph()
                flushOrdered()
                bulletBuffer.append(item)
                continue
            }

            // Ordered
            if let item = orderedMatch(trimmed) {
                flushParagraph()
                flushBullets()
                orderedBuffer.append(item)
                continue
            }

            // Paragraph
            flushBullets()
            flushOrdered()
            paragraphBuffer.append(trimmed)
        }

        flushAll()
        return blocks
    }

    private static func codeFence(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("```") else { return nil }
        let after = trimmed.dropFirst(3)
        let lang = after.trimmingCharacters(in: .whitespaces)
        return lang.isEmpty ? "" : lang
    }

    private static func headingMatch(_ line: String) -> (Int, String)? {
        var level = 0
        var index = line.startIndex
        while index < line.endIndex, line[index] == "#" {
            level += 1
            index = line.index(after: index)
        }
        guard level > 0, level <= 3 else { return nil }
        guard index < line.endIndex, line[index] == " " else { return nil }
        let rest = String(line[line.index(after: index)...])
        return (level, rest)
    }

    private static func bulletMatch(_ line: String) -> String? {
        guard line.hasPrefix("- ") || line.hasPrefix("* ") else { return nil }
        return String(line.dropFirst(2))
    }

    private static func orderedMatch(_ line: String) -> String? {
        var index = line.startIndex
        var hasDigits = false
        while index < line.endIndex, line[index].isNumber {
            hasDigits = true
            index = line.index(after: index)
        }
        guard hasDigits, index < line.endIndex, line[index] == "." else { return nil }
        index = line.index(after: index)
        guard index < line.endIndex, line[index] == " " else { return nil }
        return String(line[line.index(after: index)...])
    }
}
