import SwiftUI
import MarkdownUI

/// Renders an assistant message as full GitHub-Flavored Markdown with our
/// dark theme + syntax-highlighted code blocks.
struct MarkdownView: View {
    let text: String

    var body: some View {
        Markdown(text)
            .markdownTheme(.rae)
            .markdownCodeSyntaxHighlighter(.rae)
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension MarkdownUI.Theme {
    /// Dark theme tuned for the agent panel: headings sized down for the side
    /// panel, code blocks have a language header + copy button + syntax
    /// colors, tables render against `Theme.appBackground` with a subtle
    /// border, links pick up `Theme.accent`, etc.
    static let rae = MarkdownUI.Theme()
        // ───────────────────────────── inline text
        .text {
            ForegroundColor(Theme.textPrimary)
            FontSize(13)
        }
        .strong {
            FontWeight(.semibold)
        }
        .emphasis {
            FontStyle(.italic)
        }
        .strikethrough {
            StrikethroughStyle(.single)
            ForegroundColor(Theme.textTertiary)
        }
        .link {
            ForegroundColor(Theme.accent)
            UnderlineStyle(.single)
        }
        // Inline `code` — V3 from the design lab: brand pink text on a
        // ~12% pink tint background. Reads as a deliberate emphasis,
        // visually ties inline code to the brand without needing extra
        // chrome (borders / shadows).
        .code {
            FontFamilyVariant(.monospaced)
            FontSize(.em(0.92))
            FontWeight(.medium)
            ForegroundColor(Theme.brandPink)
            BackgroundColor(Theme.brandPink.opacity(0.12))
        }
        // ───────────────────────────── headings
        .heading1 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(18)
                    ForegroundColor(Theme.textPrimary)
                }
                .markdownMargin(top: .em(0.8), bottom: .em(0.2))
        }
        .heading2 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(16)
                    ForegroundColor(Theme.textPrimary)
                }
                .markdownMargin(top: .em(0.7), bottom: .em(0.2))
        }
        .heading3 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(14)
                    ForegroundColor(Theme.textPrimary)
                }
                .markdownMargin(top: .em(0.6), bottom: .em(0.2))
        }
        .heading4 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(13)
                    ForegroundColor(Theme.textPrimary)
                }
                .markdownMargin(top: .em(0.5), bottom: .em(0.2))
        }
        // ───────────────────────────── block elements
        .paragraph { configuration in
            configuration.label
                .fixedSize(horizontal: false, vertical: true)
                .relativeLineSpacing(.em(0.18))
                .markdownMargin(top: .em(0.3), bottom: .em(0.3))
        }
        .listItem { configuration in
            configuration.label
                .markdownMargin(top: .em(0.1))
        }
        .bulletedListMarker(.disc)
        .numberedListMarker(.decimal)
        .taskListMarker { configuration in
            Image(systemName: configuration.isCompleted ? "checkmark.square.fill" : "square")
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(configuration.isCompleted ? Theme.accent : Theme.textTertiary)
                .imageScale(.small)
        }
        .thematicBreak {
            Divider()
                .overlay(Theme.border)
                .padding(.vertical, 4)
        }
        .image { configuration in
            configuration.label
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .blockquote { configuration in
            HStack(spacing: 10) {
                Rectangle()
                    .fill(Theme.borderStrong)
                    .frame(width: 2)
                configuration.label
                    .markdownTextStyle { ForegroundColor(Theme.textSecondary) }
            }
            .markdownMargin(top: .em(0.4), bottom: .em(0.4))
        }
        // ───────────────────────────── code blocks
        .codeBlock { configuration in
            VStack(alignment: .leading, spacing: 0) {
                CodeBlockHeader(language: configuration.language, code: configuration.content)
                ScrollView(.horizontal, showsIndicators: false) {
                    configuration.label
                        .relativeLineSpacing(.em(0.18))
                        .markdownTextStyle {
                            FontFamilyVariant(.monospaced)
                            FontSize(12.5)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(Theme.appBackground)
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay {
                RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
            }
            .markdownMargin(top: .em(0.4), bottom: .em(0.4))
        }
        // Tables — V2 from the design lab: every cell bordered (subtle
        // cream stroke for inside + outside) with the header row
        // distinguished by a pink tint band. MarkdownUI's table API
        // doesn't expose per-row backgrounds, so the closest we can get
        // to a "header underline" effect is via `alternatingRows` where
        // the header row (row 0) picks up the first color. Setting both
        // colors to clear-but-different leans on the cell borders for
        // structure and the header text color for the underline cue.
        .table { configuration in
            configuration.label
                .markdownTableBorderStyle(
                    .init(
                        color: Theme.border,
                        strokeStyle: .init(lineWidth: 1)
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay {
                    RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1)
                }
                .markdownMargin(top: .em(0.4), bottom: .em(0.4))
        }
        .tableCell { configuration in
            configuration.label
                .markdownTextStyle {
                    if configuration.row == 0 {
                        FontWeight(.semibold)
                        ForegroundColor(Theme.brandPink)
                    } else {
                        ForegroundColor(Theme.textSecondary)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
        }
}

// MARK: - Code block header

private struct CodeBlockHeader: View {
    let language: String?
    let code: String

    var body: some View {
        HStack(spacing: 8) {
            if let language, !language.isEmpty {
                Text(language)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
                    .textCase(.lowercase)
            } else {
                Text("code")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
                    .textCase(.lowercase)
            }
            Spacer()
            CopyCodeButton(code: code)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Theme.elevated)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.border).frame(height: 1)
        }
    }
}

private struct CopyCodeButton: View {
    let code: String
    @State private var didCopy = false

    var body: some View {
        Button {
            let pb = NSPasteboard.general
            pb.clearContents()
            pb.setString(code, forType: .string)
            withAnimation(.easeOut(duration: 0.15)) { didCopy = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                withAnimation(.easeOut(duration: 0.2)) { didCopy = false }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: didCopy ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 10, weight: .semibold))
                Text(didCopy ? "Copied" : "Copy")
                    .font(.caption2)
            }
            .foregroundStyle(didCopy ? Theme.success : Theme.textTertiary)
        }
        .buttonStyle(.plain)
        .help("Copy code")
    }
}
