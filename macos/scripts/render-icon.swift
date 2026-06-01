#!/usr/bin/env swift

// Renders a square PNG of the rae app icon: a brand-pink rounded
// background with a cream Fraunces-italic asterisk centered on top.
//
// Usage:
//     swift scripts/render-icon.swift <font.ttf> <output.png> [size]
//
// The font path should point at the same Fraunces-Italic-VariableFont.ttf
// that ships in Sources/ReverseAPI/Resources/. Size defaults to 1024px,
// which is the largest tile the .icns needs — every other size is
// produced by `sips` downsampling from this master.

import AppKit
import CoreText
import Foundation

// MARK: - CLI

let args = CommandLine.arguments
guard args.count >= 3 else {
    fputs("usage: render-icon.swift <font.ttf> <output.png> [size]\n", stderr)
    exit(1)
}
let fontURL = URL(fileURLWithPath: args[1])
let outputURL = URL(fileURLWithPath: args[2])
let size = CGFloat(args.count >= 4 ? Int(args[3]) ?? 1024 : 1024)

// MARK: - Font registration

guard FileManager.default.fileExists(atPath: fontURL.path) else {
    fputs("error: font not found at \(fontURL.path)\n", stderr)
    exit(1)
}
var registerError: Unmanaged<CFError>?
guard CTFontManagerRegisterFontsForURL(fontURL as CFURL, .process, &registerError) else {
    let message = registerError?.takeRetainedValue().localizedDescription ?? "unknown"
    fputs("error: failed to register font: \(message)\n", stderr)
    exit(1)
}

// MARK: - Resolve italic variable Fraunces

func fourCC(_ tag: String) -> UInt32 {
    var result: UInt32 = 0
    for scalar in tag.unicodeScalars {
        result = (result << 8) | (scalar.value & 0xff)
    }
    return result
}

// macOS Big Sur+ template: visible tile = 824×824 inside the 1024
// canvas (~100pt transparent padding per side). Sizing the glyph
// against the tile (not the canvas) keeps it consistent with stock
// app icons in the Dock.
let tileInset = size * 100.0 / 1024.0
let tileSize = size - 2 * tileInset
let tileOrigin = NSPoint(x: tileInset, y: tileInset)
let glyphSize = tileSize * 0.55

// Load via CGFont rather than CTFontManagerCreateFontDescriptorsFromURL:
// the latter resolves to the file's named instances which freeze axes
// (opsz, SOFT, WONK) and silently ignore our override dictionary.
// CGFont returns the variable parent — fully overridable.
guard let dataProvider = CGDataProvider(url: fontURL as CFURL),
      let cgFont = CGFont(dataProvider) else {
    fputs("error: could not load CGFont from \(fontURL.path)\n", stderr)
    exit(1)
}
// 12° italic shear — matches the CSS-synthesised italic the web uses.
var italicSkew = CGAffineTransform(
    a: 1, b: 0,
    c: CGFloat(tan(12.0 * .pi / 180.0)), d: 1,
    tx: 0, ty: 0
)
let baseFont = CTFontCreateWithGraphicsFont(cgFont, glyphSize, &italicSkew, nil)

let variationDict: [NSNumber: NSNumber] = [
    NSNumber(value: fourCC("wght")): NSNumber(value: Double(400)),
    NSNumber(value: fourCC("opsz")): NSNumber(value: Double(144)),
    NSNumber(value: fourCC("SOFT")): NSNumber(value: Double(100)),
    NSNumber(value: fourCC("WONK")): NSNumber(value: Double(1)),
]
let descriptor = CTFontDescriptorCreateWithAttributes([
    kCTFontVariationAttribute: variationDict
] as CFDictionary)
let variableFont = CTFontCreateCopyWithAttributes(baseFont, glyphSize, &italicSkew, descriptor)

if let appliedVariations = CTFontCopyVariation(variableFont) as? [CFNumber: CFNumber] {
    print("applied variations: \(appliedVariations)")
}
print("resolved font: \(CTFontCopyPostScriptName(variableFont) as String)")

let font = variableFont as NSFont

// MARK: - Colors

let backgroundColor = NSColor(red: 0.078, green: 0.067, blue: 0.055, alpha: 1.0) // Theme.surface dark
let asteriskColor = NSColor(red: 1.0, green: 0.239, blue: 0.545, alpha: 1.0)     // Theme.brandPink dark

// MARK: - Render

let pixelSize = NSSize(width: size, height: size)
guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: Int(size),
    pixelsHigh: Int(size),
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 32
) else {
    fputs("error: could not allocate bitmap\n", stderr)
    exit(1)
}

let savedContext = NSGraphicsContext.current
defer { NSGraphicsContext.current = savedContext }
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)

let ctx = NSGraphicsContext.current!.cgContext
ctx.setShouldAntialias(true)
ctx.setShouldSmoothFonts(true)

// 22.5% corner radius on the tile (Apple's macOS Big Sur+ value).
let cornerRadius = tileSize * 0.225
let backgroundPath = NSBezierPath(
    roundedRect: NSRect(x: tileOrigin.x, y: tileOrigin.y, width: tileSize, height: tileSize),
    xRadius: cornerRadius,
    yRadius: cornerRadius
)
backgroundColor.setFill()
backgroundPath.fill()

// Use the glyph bbox (not text line metrics) for optical centering.
let ctFont = font as CTFont
let glyph = CTFontGetGlyphWithName(ctFont, "asterisk" as CFString)
var glyphs = [glyph]
var boundingRects = [CGRect.zero]
CTFontGetBoundingRectsForGlyphs(ctFont, .default, &glyphs, &boundingRects, 1)
let glyphRect = boundingRects[0]

// `CTFontGetBoundingRectsForGlyphs` returns the upright bbox — the
// italic skew shifts the glyph right by `height * tan(12°)`. Pull
// drawX left by half that to keep the sheared glyph centered.
let italicShear = CGFloat(tan(12.0 * .pi / 180.0))
let shearCorrection = (glyphRect.height * italicShear) / 2
let drawX = (size - glyphRect.width) / 2 - glyphRect.minX - shearCorrection
let drawY = (size - glyphRect.height) / 2 - glyphRect.minY

let attributes: [NSAttributedString.Key: Any] = [
    .font: font,
    .foregroundColor: asteriskColor,
]
let attrString = NSAttributedString(string: "*", attributes: attributes)
attrString.draw(at: NSPoint(x: drawX, y: drawY))

// MARK: - Write PNG

guard let pngData = bitmap.representation(using: .png, properties: [:]) else {
    fputs("error: could not encode PNG\n", stderr)
    exit(1)
}
do {
    try pngData.write(to: outputURL)
    print("✓ \(outputURL.lastPathComponent) (\(Int(size))×\(Int(size)))")
} catch {
    fputs("error: write failed: \(error.localizedDescription)\n", stderr)
    exit(1)
}
