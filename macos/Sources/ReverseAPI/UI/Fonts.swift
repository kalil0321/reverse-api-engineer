import SwiftUI
import AppKit
import CoreText
import Foundation

/// Bundled brand fonts — currently just Fraunces (italic variable) for the
/// `*` brand asterisk + "rae" wordmark + section headlines.
///
/// Body text + monospaced labels stay on SF Pro / SF Mono — shipping
/// Inter + JetBrains Mono for marginal visual gain would add ~2 MB to
/// the .app for little payoff on macOS where SF reads native.
enum BrandFont {
    /// Register the bundled font files with Core Text so SwiftUI's
    /// `.font(.custom("Fraunces", size: ...))` and the `NSFont`-based
    /// helpers below can find them. Idempotent — Core Text coalesces
    /// duplicate process-scope registrations.
    ///
    /// Call once at app launch (`AppDelegate.applicationDidFinishLaunching`)
    /// before any window appears, so the wordmark renders correctly on
    /// first paint.
    static func bootstrap() {
        let fontFiles = ["Fraunces-Italic-VariableFont"]
        for name in fontFiles {
            // SwiftPM's resource bundle uses `Resources/<file>` (not the
            // macOS-standard `Contents/Resources/`) when populated via
            // `.copy("Resources")`. Try the explicit subdirectory first,
            // fall back to a root lookup so a future Package.swift tweak
            // that puts the file at the bundle root keeps working.
            let url = Bundle.module.url(forResource: name, withExtension: "ttf", subdirectory: "Resources")
                ?? Bundle.module.url(forResource: name, withExtension: "ttf")
            guard let url else {
                print("[BrandFont] \(name).ttf not found in bundle — falling back to system font")
                continue
            }
            var error: Unmanaged<CFError>?
            if !CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
                let message = (error?.takeRetainedValue()).map { String(describing: $0) } ?? "unknown"
                print("[BrandFont] failed to register \(name): \(message)")
            }
        }
    }
}

extension Font {
    /// Fraunces Italic, our display serif. Use sparingly — wordmark,
    /// brand asterisk, section headlines ("Traffic", "Sessions").
    ///
    /// `soft` and `wonk` control the variable-font axes that give the
    /// brand asterisk its characteristic rounded-petal shape:
    /// - `soft = 100` rounds the terminals
    /// - `wonk = true` enables the alternate, more playful glyph forms
    /// - `opsz = 144` is the website's chosen optical size
    ///
    /// Defaults match the website's marquee usage. Falls back to SF
    /// Italic if the bundled font failed to register.
    static func fraunces(
        size: CGFloat,
        weight: CGFloat = 600,
        soft: CGFloat = 100,
        wonk: Bool = true,
        opsz: CGFloat = 144
    ) -> Font {
        let variations: [UInt32: Any] = [
            fourCC("wght"): weight,
            fourCC("SOFT"): soft,
            fourCC("WONK"): wonk ? 1 : 0,
            fourCC("opsz"): opsz,
        ]
        // Build a descriptor with the family + italic trait + variable
        // axes, then materialise it as NSFont so SwiftUI can wrap it.
        let descriptor = NSFontDescriptor(fontAttributes: [
            .family: "Fraunces",
            NSFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): variations,
        ]).withSymbolicTraits(.italic)
        if let nsFont = NSFont(descriptor: descriptor, size: size) {
            return Font(nsFont)
        }
        return .system(size: size, weight: .semibold).italic()
    }
}

/// Four-character code → UInt32 in the byte order Core Text expects for
/// `kCTFontVariationAxisIdentifierKey`. "wght" → 0x77676874, etc.
@inlinable
func fourCC(_ tag: String) -> UInt32 {
    var result: UInt32 = 0
    for scalar in tag.unicodeScalars {
        result = (result << 8) | (scalar.value & 0xff)
    }
    return result
}
