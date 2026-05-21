import SwiftUI
import AppKit

/// Visual tokens for the rae macOS app.
///
/// Mirrors `reverse-api-website`'s design system (see `SYSTEM_DESIGN.md`
/// at the repo root) — warm cream/ink palette, pink magenta brand
/// accent. Every token now resolves dynamically against the system
/// appearance, so the app honours macOS's dark/light setting instead of
/// being locked to dark.
///
/// Hex equivalents trail each declaration in comments — they're the
/// authoritative reference. RGB literals are SwiftUI plumbing.
enum Theme {
    // MARK: Backgrounds — warm cream / cream-dark stack

    /// Root canvas. `--color-cream` light / darker than spec in dark
    /// (user feedback: original #14110e read too "milky", deepened to
    /// #0a0806).
    static let appBackground = Color.dynamic(
        light: hex(0xfff7f0),
        dark: hex(0x0a0806)
    )
    /// Cards, panels. `--color-cream-soft`.
    static let surface = Color.dynamic(
        light: hex(0xfef8ee),
        dark: hex(0x14110e)
    )
    /// Hover backgrounds, badges, raised one tier above `surface`.
    static let elevated = Color.dynamic(
        light: hex(0xf5f2ee),
        dark: hex(0x1c1814)
    )
    /// Input fields. `--color-washed`.
    static let input = Color.dynamic(
        light: hex(0xf5f2ee),
        dark: hex(0x14110e)
    )
    /// Scrim behind modal palettes — slightly lighter than pitch black
    /// so light-mode users still see the underlying surface bleed
    /// through.
    static let overlay = Color.black.opacity(0.55)

    // MARK: Borders & dividers — ink/cream at very low alpha

    /// Default 1pt strokes. `--color-fd-border` = ink @ 10% light / cream @ 8% dark.
    static let border = Color.dynamic(
        light: Color.black.opacity(0.10),
        dark: Color.white.opacity(0.08)
    )
    /// Stronger structural separators.
    static let borderStrong = Color.dynamic(
        light: Color.black.opacity(0.18),
        dark: Color.white.opacity(0.14)
    )

    // MARK: Text — ink / cream

    /// Primary text.
    static let textPrimary = Color.dynamic(
        light: hex(0x1f1f1f),
        dark: hex(0xfff7f0)
    )
    /// Secondary text. `--color-ink-soft`.
    static let textSecondary = Color.dynamic(
        light: hex(0x1f1f1f).opacity(0.78),
        dark: hex(0xfff7f0).opacity(0.73)
    )
    /// Tertiary text (timestamps, labels, captions).
    static let textTertiary = Color.dynamic(
        light: hex(0x1f1f1f).opacity(0.55),
        dark: hex(0xfff7f0).opacity(0.55)
    )

    // MARK: Semantic accents

    /// Primary brand accent. Pink magenta. `--color-fd-primary`.
    /// Drives focus rings, primary CTAs, status dots, brand asterisk.
    static let accent = Color.dynamic(
        light: hex(0xe50d75),
        dark: hex(0xff3d8b)
    )
    /// Alias of `accent` for sites that read as "brand mark" (the
    /// `*` asterisk + "rae" wordmark) rather than generic CTA.
    static let brandPink = accent

    /// Completed / success states. Deeper mint on light bg for
    /// readability, soft mint on dark bg so it doesn't shout.
    static let success = Color.dynamic(
        light: hex(0x2d8059),
        dark: hex(0xa4d4b8)
    )
    /// Alias of `success` for explicit "completion" semantics.
    static let mint = success

    /// Warning / attention. Warm orange.
    static let warn = Color.dynamic(
        light: hex(0xb06b3e),
        dark: hex(0xd4946e)
    )

    /// Errors / destructive actions. Single value — works on both
    /// palettes with adequate contrast.
    static let danger = hex(0xe04848)

    // MARK: HTTP method palette

    /// HTTP method colors — desaturated slightly vs the original dark-only
    /// palette so they read on the cream light background without
    /// vibrating, while keeping enough difference between them for the
    /// dense traffic table.
    static let methodGet = Color.dynamic(light: hex(0x1f6fd1), dark: hex(0x64a4ff))
    static let methodPost = Color.dynamic(light: hex(0x1f8757), dark: hex(0x63d98a))
    static let methodPut = Color.dynamic(light: hex(0xb88128), dark: hex(0xf3b848))
    static let methodDelete = Color.dynamic(light: hex(0xc43d3d), dark: hex(0xf27070))
    static let methodConnect = Color.dynamic(light: hex(0x6e3fbd), dark: hex(0xae7bf6))

    // MARK: Shape radii

    /// Outer container cards (the 3-column shell).
    static let radiusCard: CGFloat = 14
    /// Inner sub-cards inside a Card.
    static let radiusInner: CGFloat = 10
    /// Inputs + small pill buttons.
    static let radiusInput: CGFloat = 8
}

// MARK: - Color helpers

extension Color {
    /// Build a SwiftUI Color that resolves to `light` under any aqua-family
    /// appearance and `dark` under any dark-aqua-family appearance. Backed
    /// by AppKit's dynamic NSColor so it also works when handed to APIs
    /// outside SwiftUI (e.g. `NSWindow.backgroundColor`).
    static func dynamic(light: Color, dark: Color) -> Color {
        Color(nsColor: NSColor(name: nil, dynamicProvider: { appearance in
            switch appearance.name {
            case .darkAqua,
                 .vibrantDark,
                 .accessibilityHighContrastDarkAqua,
                 .accessibilityHighContrastVibrantDark:
                return NSColor(dark)
            default:
                return NSColor(light)
            }
        }))
    }
}

/// Hex literal helper — `hex(0xff3d8b)` reads more naturally than the
/// RGB-as-fractions form. Alpha is always 1.0; use `.opacity(...)` for
/// translucent variants.
@inlinable
func hex(_ value: UInt32) -> Color {
    Color(
        red: Double((value >> 16) & 0xff) / 255.0,
        green: Double((value >> 8) & 0xff) / 255.0,
        blue: Double(value & 0xff) / 255.0
    )
}
