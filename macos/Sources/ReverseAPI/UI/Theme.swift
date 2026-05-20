import SwiftUI

enum Theme {
    // Backgrounds (darkest → lightest) — exploration: bumped roughly +6%
    // luminance across the dark stack so the canvas reads as warm dark grey
    // instead of near-black. Each surface keeps the same relative gap
    // (~5% between tiers) so contrast on hover/selected states is preserved.
    static let appBackground = Color(red: 0.071, green: 0.075, blue: 0.086)        // #12131A
    static let surface = Color(red: 0.106, green: 0.110, blue: 0.122)              // #1B1C1F
    static let elevated = Color(red: 0.157, green: 0.161, blue: 0.180)             // #28292E
    static let input = Color(red: 0.122, green: 0.125, blue: 0.141)                // #1F2024
    static let overlay = Color.black.opacity(0.55)

    // Borders & dividers
    static let border = Color.white.opacity(0.07)
    static let borderStrong = Color.white.opacity(0.14)

    // Text
    static let textPrimary = Color(red: 0.929, green: 0.929, blue: 0.937)          // #EDEDEF
    static let textSecondary = Color(red: 0.549, green: 0.557, blue: 0.580)        // #8C8E94
    static let textTertiary = Color(red: 0.373, green: 0.380, blue: 0.404)         // #5F6167

    // Accent colors (matched against the dark canvas)
    static let accent = Color(red: 0.231, green: 0.510, blue: 0.965)               // #3B82F6
    static let warn = Color(red: 0.941, green: 0.549, blue: 0.227)                 // #F08C3A
    static let success = Color(red: 0.298, green: 0.792, blue: 0.518)              // #4CCA84
    static let danger = Color(red: 0.949, green: 0.357, blue: 0.357)               // #F25B5B

    // Method palette (HTTP)
    static let methodGet = Color(red: 0.392, green: 0.643, blue: 1.000)            // #64A4FF
    static let methodPost = Color(red: 0.388, green: 0.851, blue: 0.541)           // #63D98A
    static let methodPut = Color(red: 0.953, green: 0.722, blue: 0.282)            // #F3B848
    static let methodDelete = Color(red: 0.949, green: 0.439, blue: 0.439)         // #F27070
    static let methodConnect = Color(red: 0.682, green: 0.482, blue: 0.965)        // #AE7BF6
}
