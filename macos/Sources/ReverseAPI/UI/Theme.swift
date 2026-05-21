import SwiftUI

/// Visual tokens for the rae macOS app.
///
/// Mirrors the dark-mode palette of `reverse-api-website` (see
/// `SYSTEM_DESIGN.md` at the repo root) so the desktop client and the
/// landing/docs site read as the same product. The app is locked to dark
/// mode via `.preferredColorScheme(.dark)`, so we only define the dark
/// variants here.
///
/// Hex equivalents are kept in the trailing comments — they're the
/// authoritative reference; the RGB literals are just SwiftUI plumbing.
enum Theme {
    // MARK: Backgrounds — warm cream-dark stack

    /// Root canvas. `--color-cream` dark variant.
    static let appBackground = Color(red: 0.078, green: 0.067, blue: 0.055)         // #14110e
    /// Cards, panels. `--color-cream-soft` dark variant.
    static let surface = Color(red: 0.110, green: 0.094, blue: 0.078)               // #1c1814
    /// Hover backgrounds, badges, raised one tier above `surface`.
    static let elevated = Color(red: 0.149, green: 0.125, blue: 0.098)              // #262019
    /// Input fields. `--color-washed` dark variant.
    static let input = Color(red: 0.102, green: 0.086, blue: 0.071)                 // #1a1612
    /// Scrim behind modal palettes.
    static let overlay = Color.black.opacity(0.55)

    // MARK: Borders & dividers — cream at very low alpha

    /// Default 1pt strokes. Matches `--color-fd-border` dark = `#fff7f014`.
    static let border = Color(red: 1.0, green: 0.969, blue: 0.941).opacity(0.08)
    /// Stronger dividers when a structural separator is needed.
    static let borderStrong = Color(red: 1.0, green: 0.969, blue: 0.941).opacity(0.14)

    // MARK: Text — cream ink on dark cream

    /// Primary text. `--color-ink` dark = cream.
    static let textPrimary = Color(red: 1.0, green: 0.969, blue: 0.941)             // #fff7f0
    /// Secondary text. `--color-ink-soft` dark ≈ cream @ 73%.
    static let textSecondary = Color(red: 1.0, green: 0.969, blue: 0.941).opacity(0.73)
    /// Tertiary text (timestamps, labels, captions).
    static let textTertiary = Color(red: 1.0, green: 0.969, blue: 0.941).opacity(0.55)

    // MARK: Semantic accents

    /// Primary brand accent. Pink magenta. `--color-fd-primary` dark.
    /// Drives focus rings, primary CTAs, status dots, agent send button.
    static let accent = Color(red: 1.0, green: 0.239, blue: 0.545)                  // #ff3d8b
    /// Alias of `accent` for sites that want to read as "brand mark" rather
    /// than generic "primary action" — e.g. the `*` asterisk + "rae" logo.
    static let brandPink = accent

    /// Completed / success states. `--color-mint` dark, softened so it
    /// sits next to cream text without shouting.
    static let success = Color(red: 0.643, green: 0.831, blue: 0.722)               // #a4d4b8
    /// Alias of `success` for explicit "completion" semantics.
    static let mint = success

    /// Warning / attention. Warm orange, derived from `--color-orange` dark.
    static let warn = Color(red: 0.831, green: 0.580, blue: 0.431)                  // #d4946e

    /// Errors / destructive actions. Kept from the previous palette — works
    /// against both cold and warm backgrounds without re-tuning.
    static let danger = Color(red: 0.949, green: 0.357, blue: 0.357)                // #F25B5B

    // MARK: HTTP method palette — intentionally vivid

    /// Kept saturated for semantic discrimination in the dense traffic
    /// table. Brand cohesion takes a back seat to "spot the method in 50ms"
    /// for this 5-color set.
    static let methodGet = Color(red: 0.392, green: 0.643, blue: 1.000)             // #64A4FF
    static let methodPost = Color(red: 0.388, green: 0.851, blue: 0.541)            // #63D98A
    static let methodPut = Color(red: 0.953, green: 0.722, blue: 0.282)             // #F3B848
    static let methodDelete = Color(red: 0.949, green: 0.439, blue: 0.439)          // #F27070
    static let methodConnect = Color(red: 0.682, green: 0.482, blue: 0.965)         // #AE7BF6

    // MARK: Shape radii

    /// Outer container cards (the 3-column shell). Slightly tighter than
    /// the web's 1.5rem to suit desktop information density.
    static let radiusCard: CGFloat = 14
    /// Inner sub-cards inside a Card.
    static let radiusInner: CGFloat = 10
    /// Inputs + small pill buttons.
    static let radiusInput: CGFloat = 8
}
