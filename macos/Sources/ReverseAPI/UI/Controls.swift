import SwiftUI
import AppKit

/// Native `NSSegmentedControl` wrapped for SwiftUI with `.capsule` segment style.
/// Used by ModeToggle and InspectorView tabs so all segmented pickers share the
/// same visual + interaction behavior (focus ring, accessibility, tracking).
struct NSSegmented: NSViewRepresentable {
    let labels: [String]
    @Binding var selection: Int

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSSegmentedControl {
        let control = NSSegmentedControl(
            labels: labels,
            trackingMode: .selectOne,
            target: context.coordinator,
            action: #selector(Coordinator.changed(_:))
        )
        control.segmentStyle = .capsule
        control.controlSize = .small
        control.font = .systemFont(ofSize: 11, weight: .medium)
        control.selectedSegment = selection
        control.appearance = NSAppearance(named: .darkAqua)
        control.setContentHuggingPriority(.required, for: .horizontal)
        control.setContentCompressionResistancePriority(.required, for: .horizontal)
        return control
    }

    func updateNSView(_ control: NSSegmentedControl, context: Context) {
        context.coordinator.parent = self
        if control.segmentCount != labels.count {
            control.segmentCount = labels.count
        }
        for (i, label) in labels.enumerated() {
            if control.label(forSegment: i) != label {
                control.setLabel(label, forSegment: i)
            }
        }
        if control.selectedSegment != selection {
            control.selectedSegment = selection
        }
    }

    final class Coordinator: NSObject {
        var parent: NSSegmented
        init(_ parent: NSSegmented) { self.parent = parent }

        @objc func changed(_ sender: NSSegmentedControl) {
            parent.selection = sender.selectedSegment
        }
    }
}

/// Visual primitives shared by all pill-shaped controls (Chip, SearchButton…).
/// Keeps hover and active states consistent across the app.
enum PillStyle {
    static let shape = Capsule()
    static let hoverBackground = Color.white.opacity(0.04)
    static let activeBackground = Color.white.opacity(0.08)
    static let activeBorder = Color.white.opacity(0.12)
}

/// Single-state pill (used for SearchButton, filter chips, etc.).
struct PillBackground: ViewModifier {
    let isActive: Bool
    let isHovering: Bool

    func body(content: Content) -> some View {
        content
            .background(background, in: Capsule())
    }

    private var background: Color {
        if isActive { return PillStyle.activeBackground }
        if isHovering { return PillStyle.hoverBackground }
        return Color.clear
    }
}

extension View {
    func pillBackground(isActive: Bool, isHovering: Bool) -> some View {
        modifier(PillBackground(isActive: isActive, isHovering: isHovering))
    }
}
