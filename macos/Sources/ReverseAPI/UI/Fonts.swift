import SwiftUI
import CoreText
import Foundation

/// Bundled brand fonts — currently just Fraunces (italic variable) for the
/// `*` brand asterisk and the "rae" wordmark.
///
/// Body text + monospaced labels stay on SF Pro / SF Mono — the desktop
/// platform already renders those natively, and shipping Inter +
/// JetBrains Mono for marginal visual gain would add ~2 MB to the .app
/// bundle for little payoff.
enum BrandFont {
    /// Register the bundled font files with Core Text so SwiftUI's
    /// `.font(.custom("Fraunces", size: ...))` can find them. Idempotent:
    /// the OS coalesces duplicate registrations within the same process.
    ///
    /// Call once at app launch (`AppDelegate.applicationDidFinishLaunching`)
    /// — before the first window appears so the wordmark renders correctly
    /// on first paint.
    static func bootstrap() {
        let fontFiles = ["Fraunces-Italic-VariableFont"]
        for name in fontFiles {
            // SwiftPM's resource bundle uses `Resources/<file>` (not the
            // macOS-standard `Contents/Resources/`) when populated via
            // `.copy("Resources")`. Try the explicit subdirectory first,
            // then fall back to a root lookup so a future Package.swift
            // tweak that puts the file at the bundle root keeps working.
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
    /// Fraunces Italic, our display serif. Use sparingly — wordmark, brand
    /// asterisk, occasional headline. Fraunces only ships here in italic;
    /// SwiftUI handles weight / size variation through the variable font
    /// axes.
    ///
    /// Falls back to SF Pro Italic if registration failed at boot.
    static func fraunces(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("Fraunces", size: size).weight(weight).italic()
    }
}
