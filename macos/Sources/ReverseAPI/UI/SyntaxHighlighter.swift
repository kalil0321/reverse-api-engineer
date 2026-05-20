import SwiftUI
import MarkdownUI

/// Lightweight, pure-Swift code-block syntax highlighter for the most common
/// languages we expect to see in agent answers: Swift, Python, JS/TS, JSON,
/// Shell, and reasonable fallbacks (HTML, CSS, SQL).
///
/// Conforms to MarkdownUI's `CodeSyntaxHighlighter` so it plugs straight into
/// `.markdownCodeSyntaxHighlighter(...)`. Tokens are detected with regular
/// expressions and styled via `AttributedString` foreground colors — no JS
/// engine, no WebKit, no transitive dependency.
struct RaeSyntaxHighlighter: CodeSyntaxHighlighter {
    func highlightCode(_ code: String, language: String?) -> Text {
        let language = (language ?? "").lowercased()
        let attributed = SyntaxColorizer.colorize(code, language: language)
        return Text(attributed)
    }
}

extension CodeSyntaxHighlighter where Self == RaeSyntaxHighlighter {
    static var rae: RaeSyntaxHighlighter { RaeSyntaxHighlighter() }
}

// MARK: - Palette

enum SyntaxPalette {
    // Colors picked to read well against `Theme.appBackground` (#050506).
    // Match a VS Code Dark+ vibe so they look familiar.
    static let keyword = Color(red: 0.78, green: 0.52, blue: 0.78)        // #C586C0 — purple-pink
    static let string = Color(red: 0.87, green: 0.66, blue: 0.42)         // #DEA86B — warm orange
    static let number = Color(red: 0.71, green: 0.81, blue: 0.66)         // #B5CEA8 — soft green
    static let comment = Color(red: 0.40, green: 0.55, blue: 0.40)        // #67925E — muted green
    static let type = Color(red: 0.31, green: 0.78, blue: 0.69)           // #4FC8B0 — teal
    static let function = Color(red: 0.86, green: 0.86, blue: 0.67)       // #DCDCAA — yellow
    static let punctuation = Color(red: 0.71, green: 0.73, blue: 0.77)    // #B5BAC4 — light gray
    static let propertyKey = Color(red: 0.61, green: 0.79, blue: 1.00)    // #9CCAFF — light blue
}

// MARK: - Colorizer

enum SyntaxColorizer {
    static func colorize(_ source: String, language: String) -> AttributedString {
        var attributed = AttributedString(source)
        attributed.foregroundColor = Theme.textPrimary

        let lang = canonicalLanguage(language)
        let rules = SyntaxRules.forLanguage(lang)

        // Apply rules in priority order: comments → strings → numbers →
        // keywords → builtins → property keys. Later rules don't overwrite
        // ranges already colored by earlier ones, which is how we avoid
        // tinting keywords inside strings or comments.
        for rule in rules {
            applyRule(rule, on: &attributed, source: source)
        }
        return attributed
    }

    private static func canonicalLanguage(_ raw: String) -> Language {
        switch raw {
        case "swift": return .swift
        case "py", "python", "python3": return .python
        case "js", "javascript", "jsx", "mjs": return .javascript
        case "ts", "typescript", "tsx": return .typescript
        case "json": return .json
        case "sh", "bash", "zsh", "shell": return .shell
        case "html", "htm", "xml": return .html
        case "css", "scss": return .css
        case "sql": return .sql
        default: return .generic
        }
    }

    private static func applyRule(_ rule: SyntaxRule, on attributed: inout AttributedString, source: String) {
        let nsSource = source as NSString
        let range = NSRange(location: 0, length: nsSource.length)
        let matches = rule.regex.matches(in: source, options: [], range: range)

        for match in matches {
            let group = rule.captureGroup ?? 0
            guard group < match.numberOfRanges else { continue }
            let r = match.range(at: group)
            guard r.location != NSNotFound, r.length > 0,
                  let attrRange = Range(r, in: source)
                    .flatMap({ Range($0, in: attributed) })
            else { continue }
            // Skip if the range already got a non-primary color from an
            // earlier (higher-priority) rule.
            if attributed[attrRange].foregroundColor != Theme.textPrimary {
                continue
            }
            attributed[attrRange].foregroundColor = rule.color
        }
    }
}

private enum Language {
    case swift, python, javascript, typescript, json, shell, html, css, sql, generic
}

private struct SyntaxRule {
    let regex: NSRegularExpression
    let color: Color
    /// Optional capture group whose range gets colored. `nil` colors the full
    /// match. Used so keyword rules with leading word boundaries don't paint
    /// the boundary character itself.
    var captureGroup: Int?
}

// MARK: - Rule sets

private enum SyntaxRules {
    static func forLanguage(_ language: Language) -> [SyntaxRule] {
        var rules: [SyntaxRule] = []

        rules.append(contentsOf: commentRules(for: language))
        rules.append(contentsOf: stringRules(for: language))
        rules.append(contentsOf: numberRules())
        rules.append(contentsOf: keywordRules(for: language))
        rules.append(contentsOf: builtinRules(for: language))
        if language == .json {
            rules.append(contentsOf: jsonPropertyKeyRules())
        }
        return rules
    }

    // MARK: comments
    private static func commentRules(for language: Language) -> [SyntaxRule] {
        var patterns: [String] = []
        switch language {
        case .swift, .javascript, .typescript, .css, .sql:
            patterns = [#"//[^\n]*"#, #"/\*[\s\S]*?\*/"#]
        case .python, .shell:
            patterns = [#"#[^\n]*"#]
        case .html:
            patterns = [#"<!--[\s\S]*?-->"#]
        case .json, .generic:
            patterns = []
        }
        return patterns.compactMap { try? rule($0, color: SyntaxPalette.comment) }
    }

    // MARK: strings
    private static func stringRules(for language: Language) -> [SyntaxRule] {
        var patterns: [String]
        switch language {
        case .python:
            patterns = [
                #""""[\s\S]*?""""#,
                #"'''[\s\S]*?'''"#,
                #"f?"(?:\\.|[^"\\\n])*""#,
                #"f?'(?:\\.|[^'\\\n])*'"#,
            ]
        case .swift, .javascript, .typescript, .json, .css, .sql:
            patterns = [
                #""(?:\\.|[^"\\\n])*""#,
                #"'(?:\\.|[^'\\\n])*'"#,
            ]
            if language == .javascript || language == .typescript || language == .swift {
                patterns.append(#"`(?:\\.|[^`\\])*`"#)
            }
        case .shell:
            patterns = [
                #""(?:\\.|[^"\\])*""#,
                #"'(?:[^'\\])*'"#,
            ]
        case .html:
            patterns = [
                #""(?:\\.|[^"\\])*""#,
                #"'(?:\\.|[^'\\])*'"#,
            ]
        case .generic:
            patterns = [
                #""(?:\\.|[^"\\\n])*""#,
                #"'(?:\\.|[^'\\\n])*'"#,
            ]
        }
        return patterns.compactMap { try? rule($0, color: SyntaxPalette.string) }
    }

    // MARK: numbers
    private static func numberRules() -> [SyntaxRule] {
        let patterns = [
            #"\b0x[0-9A-Fa-f]+\b"#,
            #"\b\d+\.\d+(?:[eE][+-]?\d+)?\b"#,
            #"\b\d+\b"#,
        ]
        return patterns.compactMap { try? rule($0, color: SyntaxPalette.number) }
    }

    // MARK: keywords
    private static func keywordRules(for language: Language) -> [SyntaxRule] {
        let words = keywords(for: language)
        guard !words.isEmpty else { return [] }
        let pattern = "\\b(?:" + words.joined(separator: "|") + ")\\b"
        return [try? rule(pattern, color: SyntaxPalette.keyword)].compactMap { $0 }
    }

    private static func keywords(for language: Language) -> [String] {
        switch language {
        case .swift:
            return [
                "associatedtype", "class", "deinit", "enum", "extension", "fileprivate",
                "func", "import", "init", "inout", "internal", "let", "open", "operator",
                "private", "protocol", "public", "rethrows", "static", "struct", "subscript",
                "typealias", "var", "break", "case", "continue", "default", "defer", "do",
                "else", "fallthrough", "for", "guard", "if", "in", "repeat", "return",
                "switch", "where", "while", "as", "catch", "is", "nil", "self", "Self",
                "super", "throw", "throws", "true", "false", "try", "async", "await",
                "actor", "any", "some", "@MainActor", "@Observable",
            ]
        case .python:
            return [
                "False", "None", "True", "and", "as", "assert", "async", "await",
                "break", "class", "continue", "def", "del", "elif", "else", "except",
                "finally", "for", "from", "global", "if", "import", "in", "is", "lambda",
                "nonlocal", "not", "or", "pass", "raise", "return", "try", "while",
                "with", "yield", "match", "case",
            ]
        case .javascript, .typescript:
            var base = [
                "var", "let", "const", "function", "return", "if", "else", "for", "while",
                "do", "switch", "case", "default", "break", "continue", "class", "extends",
                "new", "delete", "typeof", "instanceof", "in", "of", "this", "super",
                "import", "export", "from", "as", "async", "await", "try", "catch",
                "finally", "throw", "yield", "void", "null", "undefined", "true", "false",
                "static", "get", "set",
            ]
            if language == .typescript {
                base.append(contentsOf: [
                    "type", "interface", "enum", "implements", "readonly", "public",
                    "private", "protected", "abstract", "declare", "namespace", "satisfies",
                    "keyof", "infer", "is",
                ])
            }
            return base
        case .json:
            return ["true", "false", "null"]
        case .shell:
            return [
                "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
                "case", "esac", "function", "return", "exit", "in", "local", "export",
                "source", "set", "unset", "alias", "readonly", "declare",
            ]
        case .sql:
            return [
                "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "INSERT", "INTO", "VALUES",
                "UPDATE", "SET", "DELETE", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
                "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "AS", "ON", "NULL",
                "CREATE", "TABLE", "DROP", "ALTER", "INDEX", "PRIMARY", "KEY", "FOREIGN",
            ]
        case .css:
            return []
        case .html:
            return []
        case .generic:
            return []
        }
    }

    // MARK: builtins / types
    private static func builtinRules(for language: Language) -> [SyntaxRule] {
        switch language {
        case .swift:
            return [
                try? rule(#"\b(?:String|Int|Double|Float|Bool|Array|Dictionary|Set|Optional|Void|Never|Result|URL|Data|Date|UUID|Color|View|Text|Image|VStack|HStack|ZStack|Button|TextField|List|ScrollView|NavigationStack|EnvironmentValues)\b"#, color: SyntaxPalette.type),
            ].compactMap { $0 }
        case .python:
            return [
                try? rule(#"\b(?:print|len|range|str|int|float|bool|list|dict|set|tuple|type|isinstance|getattr|setattr|hasattr|open|input|enumerate|zip|map|filter|sorted|reversed|sum|min|max|abs|round|self|cls|Exception|ValueError|TypeError|KeyError|IndexError|AttributeError)\b"#, color: SyntaxPalette.type),
            ].compactMap { $0 }
        case .javascript, .typescript:
            return [
                try? rule(#"\b(?:console|window|document|process|module|require|globalThis|JSON|Math|Date|Promise|Array|Object|String|Number|Boolean|Map|Set|WeakMap|WeakSet|Symbol|Error|TypeError|RangeError|Proxy|Reflect)\b"#, color: SyntaxPalette.type),
            ].compactMap { $0 }
        case .shell:
            return [
                try? rule(#"\b(?:echo|cd|ls|grep|sed|awk|cat|head|tail|find|xargs|cp|mv|rm|mkdir|chmod|chown|curl|wget|git|npm|pip|python|node|brew|sudo|env|export|which)\b"#, color: SyntaxPalette.function),
            ].compactMap { $0 }
        default:
            return []
        }
    }

    // MARK: JSON property keys (the "key" before ":")
    private static func jsonPropertyKeyRules() -> [SyntaxRule] {
        // Match "key" before a colon. We've already colored strings as
        // string-color; this rule re-paints keys via a higher-priority
        // detection. Use capture group 1 to skip the trailing quote+colon.
        let pattern = #""((?:[^"\\]|\\.)*)"\s*:"#
        if let r = try? NSRegularExpression(pattern: pattern) {
            return [SyntaxRule(regex: r, color: SyntaxPalette.propertyKey, captureGroup: 1)]
        }
        return []
    }

    // MARK: helper
    private static func rule(_ pattern: String, color: Color) throws -> SyntaxRule {
        let regex = try NSRegularExpression(pattern: pattern, options: [.dotMatchesLineSeparators])
        return SyntaxRule(regex: regex, color: color)
    }
}
