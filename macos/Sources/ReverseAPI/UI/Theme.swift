import SwiftUI

enum Theme {
    // Backgrounds (darkest → lightest) — near-black palette
    static let appBackground = Color(red: 0.020, green: 0.020, blue: 0.024)        // #050506
    static let surface = Color(red: 0.043, green: 0.043, blue: 0.051)              // #0B0B0D
    static let elevated = Color(red: 0.086, green: 0.086, blue: 0.102)             // #16161A
    static let input = Color(red: 0.059, green: 0.059, blue: 0.067)                // #0F0F11
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
