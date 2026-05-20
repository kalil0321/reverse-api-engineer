import AppKit
import SwiftUI
import ReverseAPIProxy

/// Traffic list rendered as a vertical stack of compact two-line rows. The
/// previous fixed-column tabular layout broke when the traffic card got
/// narrow (paths and hosts collided, columns wrapped). The new row keeps
/// host on top + path below in a flex middle column so the row stays
/// readable down to ~240pt wide.
struct TrafficListView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 0) {
            TrafficListHeader(
                visibleCount: filteredFlows.count,
                visibleIDs: filteredFlows.map(\.id)
            )
            ThinDivider()
            if state.store.flows.isEmpty {
                EmptyTrafficState()
            } else if filteredFlows.isEmpty {
                EmptyFilterState()
            } else {
                TrafficRowList(flows: filteredFlows)
            }
        }
        .background(Theme.surface)
    }

    private var filteredFlows: [CapturedFlow] {
        state.store.flows.filter { state.filter.matches($0) }
    }
}

// MARK: - Header

private struct TrafficListHeader: View {
    @Environment(AppState.self) private var state
    let visibleCount: Int
    let visibleIDs: [UUID]

    var body: some View {
        HStack(spacing: 10) {
            SelectAllCheckbox(visibleIDs: visibleIDs)
            Text("Traffic")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            Text("\(visibleCount)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textTertiary)
                .padding(.horizontal, 6)
                .padding(.vertical, 1)
                .background(Theme.elevated, in: Capsule())
            Spacer()
            FilterButton(hasActiveFilters: hasActiveFilters)
            DeleteAllButton()
        }
        // Same horizontal padding as TrafficRow so the header select-all
        // checkbox sits in the same column as the per-row checkboxes.
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    private var hasActiveFilters: Bool {
        let f = state.filter
        return !f.search.isEmpty
            || f.onlyErrors
            || !f.resourceKinds.isEmpty
            || !f.methods.isEmpty
            || !f.statusBuckets.isEmpty
            || !f.hosts.isEmpty
    }
}

// MARK: - Filter button + popover

private struct FilterButton: View {
    let hasActiveFilters: Bool
    @State private var isShowing = false

    var body: some View {
        Button {
            isShowing.toggle()
        } label: {
            ZStack(alignment: .topTrailing) {
                Image(systemName: "line.3.horizontal.decrease")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
                if hasActiveFilters {
                    Circle()
                        .fill(Theme.success)
                        .frame(width: 6, height: 6)
                        .offset(x: 1, y: -1)
                }
            }
        }
        .buttonStyle(.plain)
        .help(hasActiveFilters ? "Filter traffic · active" : "Filter traffic")
        .popover(isPresented: $isShowing, arrowEdge: .top) {
            FilterPopoverContent()
                .frame(width: 320)
        }
    }
}

private struct FilterPopoverContent: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var bindable = state
        VStack(alignment: .leading, spacing: 12) {
            // Text filter
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textTertiary)
                TrafficSearchField(text: $bindable.filter.search)
                    .frame(maxWidth: .infinity)
                    .frame(height: 16)
                if !state.filter.search.isEmpty {
                    Button {
                        state.filter.search = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Theme.input, in: RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 10) {
                FilterSectionLabel("Type")
                ResourceKindRow(selection: $bindable.filter.resourceKinds)
            }

            if !state.store.methodOptions.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    FilterSectionLabel("Method")
                    MethodRow(options: state.store.methodOptions, selection: $bindable.filter.methods)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                FilterSectionLabel("Status")
                StatusRow(selection: $bindable.filter.statusBuckets)
            }

            Toggle(isOn: $bindable.filter.onlyErrors) {
                Text("Errors only")
                    .font(.callout)
                    .foregroundStyle(Theme.textPrimary)
            }
            .toggleStyle(.switch)
            .controlSize(.small)
            .tint(Theme.success)

            if hasActiveFilters {
                Divider().overlay(Theme.border)
                Button {
                    state.filter = TrafficFilter()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 10, weight: .semibold))
                        Text("Reset filters")
                            .font(.callout)
                    }
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(14)
    }

    private var hasActiveFilters: Bool {
        let f = state.filter
        return !f.search.isEmpty
            || f.onlyErrors
            || !f.resourceKinds.isEmpty
            || !f.methods.isEmpty
            || !f.statusBuckets.isEmpty
            || !f.hosts.isEmpty
    }
}

private struct FilterSectionLabel: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(Theme.textTertiary)
            .tracking(0.6)
    }
}

// MARK: - Text filter (custom NSTextField — not SwiftUI's default searchable)

private struct TrafficSearchField: NSViewRepresentable {
    @Binding var text: String

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSTextField {
        let field = NSTextField()
        field.delegate = context.coordinator
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = .systemFont(ofSize: 12)
        field.textColor = .white
        field.placeholderAttributedString = NSAttributedString(
            string: "Filter by host, path, method…",
            attributes: [
                .font: NSFont.systemFont(ofSize: 12),
                .foregroundColor: NSColor.white.withAlphaComponent(0.32),
            ]
        )
        field.stringValue = text
        field.appearance = NSAppearance(named: .darkAqua)
        field.cell?.usesSingleLineMode = true
        field.cell?.wraps = false
        field.cell?.isScrollable = true
        return field
    }

    func updateNSView(_ field: NSTextField, context: Context) {
        context.coordinator.parent = self
        if field.stringValue != text {
            field.stringValue = text
        }
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: TrafficSearchField

        init(_ parent: TrafficSearchField) { self.parent = parent }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else { return }
            parent.text = field.stringValue
        }

        func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.cancelOperation(_:)) {
                parent.text = ""
                return true
            }
            return false
        }
    }
}

private struct ResourceKindRow: View {
    @Binding var selection: Set<TrafficFilter.ResourceKind>

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(TrafficFilter.ResourceKind.allCases) { kind in
                    FilterChip(
                        title: kind.rawValue,
                        isSelected: selection.contains(kind)
                    ) {
                        if selection.contains(kind) { selection.remove(kind) }
                        else { selection.insert(kind) }
                    }
                }
            }
        }
    }
}

private struct MethodRow: View {
    let options: [String]
    @Binding var selection: Set<String>

    var body: some View {
        if options.isEmpty {
            EmptyView()
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(options, id: \.self) { method in
                        FilterChip(
                            title: method,
                            isSelected: selection.contains(method),
                            tint: methodTint(method)
                        ) {
                            if selection.contains(method) { selection.remove(method) }
                            else { selection.insert(method) }
                        }
                    }
                }
            }
        }
    }

    private func methodTint(_ method: String) -> Color {
        switch method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        case "CONNECT": return Theme.methodConnect
        default: return Theme.textSecondary
        }
    }
}

private struct StatusRow: View {
    @Binding var selection: Set<TrafficFilter.StatusBucket>

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(TrafficFilter.StatusBucket.allCases) { bucket in
                    FilterChip(
                        title: bucket.rawValue,
                        isSelected: selection.contains(bucket),
                        tint: statusTint(bucket)
                    ) {
                        if selection.contains(bucket) { selection.remove(bucket) }
                        else { selection.insert(bucket) }
                    }
                }
            }
        }
    }

    private func statusTint(_ bucket: TrafficFilter.StatusBucket) -> Color {
        switch bucket {
        case .informational: return Theme.textSecondary
        case .success: return Theme.success
        case .redirect: return Theme.methodGet
        case .clientError: return Theme.methodPut
        case .serverError: return Theme.danger
        }
    }
}

private struct FilterChip: View {
    let title: String
    let isSelected: Bool
    var tint: Color = Theme.textPrimary
    let action: () -> Void
    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.medium))
                .foregroundStyle(foreground)
                .padding(.horizontal, 9)
                .padding(.vertical, 3)
                .background(background, in: Capsule())
                .overlay {
                    Capsule().stroke(borderColor, lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }

    private var foreground: Color {
        isSelected ? tint : Theme.textSecondary
    }

    private var background: Color {
        if isSelected { return tint.opacity(0.18) }
        if isHovering { return Color.white.opacity(0.05) }
        return Color.clear
    }

    private var borderColor: Color {
        if isSelected { return tint.opacity(0.5) }
        return Theme.border
    }
}

private struct DeleteAllButton: View {
    @Environment(AppState.self) private var state

    var body: some View {
        Button {
            state.clearFlows()
        } label: {
            Image(systemName: "trash")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(state.store.flows.isEmpty ? Theme.textTertiary : Theme.textPrimary)
                .frame(width: 22, height: 22)
                .background(Theme.elevated, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(state.store.flows.isEmpty)
        .help("Delete all captured traffic")
    }
}

private struct SelectAllCheckbox: View {
    @Environment(AppState.self) private var state
    let visibleIDs: [UUID]

    var body: some View {
        Button(action: toggle) {
            Image(systemName: glyph)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 18, height: 18)
        }
        .buttonStyle(.plain)
        .help(allSelected
              ? "Clear agent selection"
              : "Select all visible rows for the agent")
    }

    private var allSelected: Bool {
        !visibleIDs.isEmpty && visibleIDs.allSatisfy { state.agentSelection.contains($0) }
    }

    private var someSelected: Bool {
        visibleIDs.contains(where: { state.agentSelection.contains($0) })
    }

    private var glyph: String {
        if allSelected { return "checkmark.square.fill" }
        if someSelected { return "minus.square.fill" }
        return "square"
    }

    private var tint: Color {
        (allSelected || someSelected) ? Theme.textPrimary : Theme.textTertiary
    }

    private func toggle() {
        if allSelected {
            visibleIDs.forEach { state.agentSelection.remove($0) }
        } else {
            visibleIDs.forEach { state.agentSelection.insert($0) }
        }
    }
}

// MARK: - Rows

private struct TrafficRowList: View {
    @Environment(AppState.self) private var state
    let flows: [CapturedFlow]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(flows) { flow in
                        TrafficRow(
                            flow: flow,
                            isSelected: state.selectedFlowID == flow.id
                        ) {
                            state.selectedFlowID = flow.id
                        }
                        .id(flow.id)
                    }
                }
            }
            .onChange(of: state.selectedFlowID) { _, new in
                guard let new else { return }
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo(new, anchor: .center)
                }
            }
        }
    }
}

private struct TrafficRow: View {
    @Environment(AppState.self) private var state
    let flow: CapturedFlow
    let isSelected: Bool
    let onSelect: () -> Void

    @State private var isHovering = false

    private var isCheckedForAgent: Bool {
        state.agentSelection.contains(flow.id)
    }

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 10) {
                AgentCheckbox(isOn: isCheckedForAgent) {
                    if state.agentSelection.contains(flow.id) {
                        state.agentSelection.remove(flow.id)
                    } else {
                        state.agentSelection.insert(flow.id)
                    }
                }

                MethodBadge(method: flow.method)
                    .frame(width: 46, alignment: .leading)

                VStack(alignment: .leading, spacing: 1) {
                    Text(flow.host)
                        .font(.callout)
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(flow.path)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .trailing, spacing: 1) {
                    StatusBadge(status: flow.responseStatus, error: flow.error)
                    Text(flow.startedAt, format: .dateTime.hour().minute().second())
                        .font(.system(size: 10, weight: .regular, design: .monospaced))
                        .foregroundStyle(Theme.textTertiary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity)
            .background(background)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
        }
        .contextMenu {
            if isCheckedForAgent {
                Button("Remove from agent selection") {
                    state.agentSelection.remove(flow.id)
                }
            } else {
                Button("Add to agent selection") {
                    state.agentSelection.insert(flow.id)
                }
            }
            Divider()
            Button("Delete", role: .destructive) {
                state.deleteFlows([flow.id])
            }
        }
    }

    private var background: Color {
        if isSelected { return Theme.elevated }
        if isHovering { return Color.white.opacity(0.03) }
        return Color.clear
    }
}

private struct AgentCheckbox: View {
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: isOn ? "checkmark.square.fill" : "square")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(isOn ? Theme.textPrimary : Theme.textTertiary)
                .frame(width: 18, height: 18)
        }
        .buttonStyle(.plain)
        .help(isOn ? "Remove from agent selection" : "Add to agent selection")
    }
}

private struct MethodBadge: View {
    let method: String

    var body: some View {
        Text(method)
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(color)
            .lineLimit(1)
    }

    private var color: Color {
        switch method {
        case "GET": return Theme.methodGet
        case "POST": return Theme.methodPost
        case "PUT", "PATCH": return Theme.methodPut
        case "DELETE": return Theme.methodDelete
        case "CONNECT": return Theme.methodConnect
        default: return Theme.textSecondary
        }
    }
}

private struct StatusBadge: View {
    let status: Int?
    let error: String?

    var body: some View {
        if let error {
            Text("ERR")
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .foregroundStyle(Theme.danger)
                .help(error)
        } else if let status {
            Text("\(status)")
                .font(.system(.callout, design: .monospaced).weight(.medium))
                .foregroundStyle(color(for: status))
        } else {
            Text("…")
                .foregroundStyle(Theme.textTertiary)
        }
    }

    private func color(for status: Int) -> Color {
        switch status {
        case 200..<300: return Theme.success
        case 300..<400: return Theme.methodGet
        case 400..<500: return Theme.methodPut
        case 500..<600: return Theme.danger
        default: return Theme.textSecondary
        }
    }
}

// MARK: - Empty states

private struct EmptyTrafficState: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: state.isCapturing ? "dot.radiowaves.left.and.right" : "waveform.path.ecg")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Theme.textTertiary)

            VStack(spacing: 4) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text(message)
                    .font(.callout)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var title: String {
        if state.isCapturing, !state.systemProxyEnabled { return "Manual capture is running" }
        if state.isCapturing { return "Waiting for traffic" }
        return "No traffic captured"
    }

    private var message: String {
        if state.isCapturing, !state.systemProxyEnabled {
            return "Only clients configured to use the proxy will appear here."
        }
        if state.isCapturing, !state.caTrustInstalled {
            return "HTTP shows up immediately. Trust the CA to inspect HTTPS."
        }
        if state.isCapturing {
            return "Open an app or browser to make a request."
        }
        return "Press Record to start capturing."
    }
}

private struct EmptyFilterState: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(Theme.textTertiary)
            Text("No matching traffic")
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            Text("Clear or loosen the current filters.")
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
