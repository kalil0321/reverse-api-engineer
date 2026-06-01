import SwiftUI
import AppKit

struct ClaudeMark: View {
    var size: CGFloat = 14

    var body: some View {
        if let image = Self.loadImage(targetSize: size) {
            Image(nsImage: image)
                .resizable()
                .interpolation(.high)
                .frame(width: size, height: size)
        } else {
            Circle()
                .fill(Color(red: 0.85, green: 0.46, blue: 0.34))
                .frame(width: size, height: size)
        }
    }

    /// `NSImage(contentsOf:)` returns the SVG's intrinsic viewBox size;
    /// `.resizable()` + `.frame(...)` don't override it for vector NSImages.
    /// Setting `image.size` here is what actually constrains the render.
    private static func loadImage(targetSize: CGFloat) -> NSImage? {
        let url = Bundle.module.url(forResource: "claude-logo", withExtension: "svg", subdirectory: "Resources")
            ?? Bundle.module.url(forResource: "claude-logo", withExtension: "svg")
        guard let url, let image = NSImage(contentsOf: url) else { return nil }
        image.size = NSSize(width: targetSize, height: targetSize)
        return image
    }
}

typealias AnthropicMark = ClaudeMark
