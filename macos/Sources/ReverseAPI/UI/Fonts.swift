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
    /// Cached CGFont parent of the variable italic Fraunces — loaded
    /// from the bundle once at bootstrap so every `Font.fraunces(...)`
    /// call can apply variations on top of it without re-reading the
    /// file. The CGFont route is what unlocks the full variable space
    /// (opsz=9…144, etc.); the named-instance descriptors that
    /// `CTFontManagerCreateFontDescriptorsFromURL` returns all have
    /// `opsz=9` pinned and silently ignore opsz / SOFT / WONK overrides.
    fileprivate static var cachedCGFont: CGFont?

    /// Register the bundled font files with Core Text so SwiftUI's
    /// `.font(.custom("Fraunces", size: ...))` and the `NSFont`-based
    /// helpers below can find them. Idempotent — Core Text coalesces
    /// duplicate process-scope registrations.
    ///
    /// Call once at app launch (`AppDelegate.applicationDidFinishLaunching`)
    /// before any window appears, so the wordmark renders correctly on
    /// first paint.
    static func bootstrap() {
        // Roman Fraunces variable font (no dedicated italic faces). The
        // companion website loads the same file via
        // `next/font/google → Fraunces({ axes: ['opsz','SOFT','WONK'] })`
        // without `style: ['italic']`, and synthesises italic in CSS via
        // the browser's automatic 12°-ish skew transform. We do the same
        // (see `Font.fraunces(...)` below) so the wordmark renders with
        // identical glyph shapes to the web instead of using the
        // dedicated-italic-face designs.
        let fontFiles = ["Fraunces-VariableFont"]
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
                continue
            }
            // Also cache the CGFont so `Font.fraunces(...)` can route
            // through `CTFontCreateCopyWithAttributes` on the variable
            // parent (which honours opsz / SOFT / WONK / wght overrides)
            // rather than landing on one of the registered named
            // instances (all pinned to opsz=9 — see comment on
            // `cachedCGFont`).
            if let provider = CGDataProvider(url: url as CFURL),
               let cgFont = CGFont(provider) {
                Self.cachedCGFont = cgFont
            } else {
                print("[BrandFont] could not build CGFont parent — variable axes will fall back")
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
        // Variations dict in the exact CFNumber/CFNumber shape Core Text
        // expects. NSNumber bridging handles the conversion correctly
        // here; the bare `[UInt32: Any]` form ended up encoded as the
        // wrong CF type and silently dropped some axes.
        let variations: [NSNumber: NSNumber] = [
            NSNumber(value: fourCC("wght")): NSNumber(value: Double(weight)),
            NSNumber(value: fourCC("opsz")): NSNumber(value: Double(opsz)),
            NSNumber(value: fourCC("SOFT")): NSNumber(value: Double(soft)),
            NSNumber(value: fourCC("WONK")): NSNumber(value: Double(wonk ? 1 : 0)),
        ]
        // Preferred path: apply variations on the cached CGFont parent
        // and pass a CSS-style italic skew matrix so the roman glyphs
        // lean ~12°, matching what the browser does when CSS asks for
        // italic on a font that has no dedicated italic face. The skew
        // is applied at glyph-render time (transform parameter of
        // CTFontCreateWithGraphicsFont), so SwiftUI doesn't need to
        // know about it.
        if let cgFont = BrandFont.cachedCGFont {
            var italicSkew = CGAffineTransform(
                a: 1, b: 0,
                // `tan(12°) ≈ 0.213` — the horizontal shear that
                // approximates the synthesised italic angle used by
                // WebKit / Blink / Gecko for non-italic faces.
                c: CGFloat(tan(12.0 * .pi / 180.0)), d: 1,
                tx: 0, ty: 0
            )
            let baseFont = CTFontCreateWithGraphicsFont(cgFont, size, &italicSkew, nil)
            let descriptor = CTFontDescriptorCreateWithAttributes([
                kCTFontVariationAttribute: variations
            ] as CFDictionary)
            let variableFont = CTFontCreateCopyWithAttributes(baseFont, size, &italicSkew, descriptor)
            return Font(variableFont as NSFont)
        }
        // Fallback: family + italic trait + variations on a regular
        // descriptor. Used only if the CGFont cache failed to populate
        // at bootstrap (e.g. font file unreadable). The asterisk will
        // pick up the 9pt design, but at least we still get Fraunces
        // italic glyphs.
        let descriptor = NSFontDescriptor(fontAttributes: [
            .family: "Fraunces",
            NSFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): variations,
        ]).withSymbolicTraits(.italic)
        if let nsFont = NSFont(descriptor: descriptor, size: size),
           nsFont.fontName.lowercased().contains("fraunces") {
            return Font(nsFont)
        }
        return .system(size: size).italic()
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
