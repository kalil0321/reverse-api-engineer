import SwiftUI
import MarkdownUI

/// Thin wrapper around MarkdownUI's `Markdown` view so the rest of the app
/// keeps its previous import (`MarkdownView(text:)`). Themed against our
/// dark palette so headings, code blocks, lists, links, etc. all match the
/// rest of the agent panel.
struct MarkdownView: View {
    let text: String

    var body: some View {
        Markdown(text)
            .markdownTheme(.rae)
            .markdownTextStyle {
                ForegroundColor(Theme.textPrimary)
                FontSize(13)
            }
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private extension Theme {
    @MainActor static var monospacedFont: Font {
        .system(.callout, design: .monospaced)
    }
}

extension MarkdownUI.Theme {
    /// Dark theme tuned for the agent panel: no extra paragraph spacing on
    /// top of MarkdownUI's defaults, headings sized down for the side panel,
    /// inline code and code blocks render against `Theme.appBackground`,
    /// blockquotes get a subtle left bar.
    static let rae = MarkdownUI.Theme()
        .text {
            ForegroundColor(Theme.textPrimary)
            FontSize(13)
        }
        .strong {
            FontWeight(.semibold)
        }
        .link {
            ForegroundColor(Theme.accent)
            UnderlineStyle(.single)
        }
        .code {
            FontFamilyVariant(.monospaced)
            FontSize(.em(0.92))
            ForegroundColor(Theme.textPrimary)
            BackgroundColor(Color.white.opacity(0.08))
        }
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
        .codeBlock { configuration in
            VStack(alignment: .leading, spacing: 0) {
                if let language = configuration.language, !language.isEmpty {
                    HStack {
                        Text(language)
                            .font(.caption2.monospaced())
                            .foregroundStyle(Theme.textTertiary)
                        Spacer()
                        Button {
                            let pb = NSPasteboard.general
                            pb.clearContents()
                            pb.setString(configuration.content, forType: .string)
                        } label: {
                            Image(systemName: "doc.on.doc")
                                .font(.caption2)
                                .foregroundStyle(Theme.textTertiary)
                        }
                        .buttonStyle(.plain)
                        .help("Copy code")
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Theme.elevated)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    configuration.label
                        .relativeLineSpacing(.em(0.15))
                        .markdownTextStyle {
                            FontFamilyVariant(.monospaced)
                            FontSize(12.5)
                            ForegroundColor(Theme.textPrimary)
                        }
                        .padding(10)
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
        .blockquote { configuration in
            HStack(spacing: 10) {
                Rectangle()
                    .fill(Theme.border)
                    .frame(width: 2)
                configuration.label
                    .markdownTextStyle { ForegroundColor(Theme.textSecondary) }
            }
            .markdownMargin(top: .em(0.4), bottom: .em(0.4))
        }
}
