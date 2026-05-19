import SwiftUI
import ReverseAPIProxy

struct TrafficListView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        @Bindable var bindable = state
        VStack(spacing: 0) {
            FilterBar(
                filter: $bindable.filter,
                hostOptions: hostOptions,
                methodOptions: methodOptions,
                totalCount: state.store.flows.count,
                visibleCount: filteredFlows.count
            )
            Divider()
            ZStack {
                table
                if state.store.flows.isEmpty {
                    EmptyTrafficState()
                } else if filteredFlows.isEmpty {
                    EmptyFilterState()
                }
            }
        }
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(.separator.opacity(0.5), lineWidth: 1)
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var filteredFlows: [CapturedFlow] {
        state.store.flows.filter { state.filter.matches($0) }
    }

    private var hostOptions: [String] {
        Array(Set(state.store.flows.map(\.host))).sorted()
    }

    private var methodOptions: [String] {
        Array(Set(state.store.flows.map(\.method))).sorted()
    }

    private var table: some View {
        @Bindable var bindable = state
        return Table(filteredFlows, selection: $bindable.selectedFlowID) {
            TableColumn("Time") { flow in
                Text(flow.startedAt, format: .dateTime.hour().minute().second())
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .width(min: 70, ideal: 80)

            TableColumn("Method") { flow in
                MethodBadge(method: flow.method)
            }
            .width(min: 60, ideal: 70)

            TableColumn("Type") { flow in
                ResourceKindBadge(kind: TrafficFilter.resourceKind(for: flow))
            }
            .width(min: 74, ideal: 86)

            TableColumn("Host") { flow in
                Text(flow.host)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .width(min: 120, ideal: 200)

            TableColumn("Path") { flow in
                Text(flow.path)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .font(.system(.callout, design: .monospaced))
            }
            .width(min: 160, ideal: 320)

            TableColumn("Status") { flow in
                StatusBadge(status: flow.responseStatus, error: flow.error)
            }
            .width(min: 60, ideal: 70)

            TableColumn("Size") { flow in
                Text(byteString(flow.responseBody.count))
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .width(min: 60, ideal: 80)

            TableColumn("Duration") { flow in
                Text(durationString(flow))
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .width(min: 70, ideal: 80)
        }
    }

    private func byteString(_ count: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(count))
    }

    private func durationString(_ flow: CapturedFlow) -> String {
        guard let finished = flow.finishedAt else { return "…" }
        let interval = finished.timeIntervalSince(flow.startedAt)
        if interval < 1 {
            return String(format: "%.0f ms", interval * 1000)
        }
        return String(format: "%.2f s", interval)
    }
}

private struct FilterBar: View {
    @Binding var filter: TrafficFilter
    let hostOptions: [String]
    let methodOptions: [String]
    let totalCount: Int
    let visibleCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Traffic")
                        .font(.title3.weight(.semibold))
                    Text(countLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }

                Spacer()

                searchField
                    .frame(width: 300)

                filterMenu
                if activeFilterCount > 0 {
                    Button {
                        filter = TrafficFilter()
                    } label: {
                        Label("Reset", systemImage: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.secondary)
                    .help("Clear \(activeFilterCount) active filters")
                }
            }

            ResourceKindBar(selectedKinds: $filter.resourceKinds)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Search URL, host, or method", text: $filter.search)
                .textFieldStyle(.plain)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 7))
    }

    private var filterMenu: some View {
        Menu {
            Toggle("Errors only", isOn: $filter.onlyErrors)
            Divider()
            Section("Types") {
                ForEach(TrafficFilter.ResourceKind.allCases) { kind in
                    toggleResource(kind)
                }
            }
            Section("Methods") {
                ForEach(methodOptions, id: \.self) { method in
                    toggle(method, in: \.methods)
                }
            }
            Section("Hosts") {
                ForEach(hostOptions, id: \.self) { host in
                    toggle(host, in: \.hosts)
                }
            }
            Section("Status") {
                ForEach(TrafficFilter.StatusBucket.allCases) { bucket in
                    toggleBucket(bucket)
                }
            }
            Divider()
            Button("Reset") { filter = TrafficFilter() }
        } label: {
            Label("Filters", systemImage: "line.3.horizontal.decrease")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var countLabel: String {
        if activeFilterCount > 0 {
            return "\(visibleCount) of \(totalCount) shown"
        }
        return "\(totalCount) captured"
    }

    private var activeFilterCount: Int {
        var count = 0
        if !filter.search.isEmpty { count += 1 }
        if filter.onlyErrors { count += 1 }
        count += filter.hosts.count
        count += filter.methods.count
        count += filter.statusBuckets.count
        count += filter.resourceKinds.count
        return count
    }

    private func toggle(_ value: String, in keyPath: WritableKeyPath<TrafficFilter, Set<String>>) -> some View {
        Button {
            if filter[keyPath: keyPath].contains(value) {
                filter[keyPath: keyPath].remove(value)
            } else {
                filter[keyPath: keyPath].insert(value)
            }
        } label: {
            HStack {
                Image(systemName: filter[keyPath: keyPath].contains(value) ? "checkmark.square.fill" : "square")
                Text(value)
            }
        }
    }

    private func toggleBucket(_ bucket: TrafficFilter.StatusBucket) -> some View {
        Button {
            if filter.statusBuckets.contains(bucket) {
                filter.statusBuckets.remove(bucket)
            } else {
                filter.statusBuckets.insert(bucket)
            }
        } label: {
            HStack {
                Image(systemName: filter.statusBuckets.contains(bucket) ? "checkmark.square.fill" : "square")
                Text(bucket.rawValue)
            }
        }
    }

    private func toggleResource(_ kind: TrafficFilter.ResourceKind) -> some View {
        Button {
            if filter.resourceKinds.contains(kind) {
                filter.resourceKinds.remove(kind)
            } else {
                filter.resourceKinds.insert(kind)
            }
        } label: {
            HStack {
                Image(systemName: filter.resourceKinds.contains(kind) ? "checkmark.square.fill" : "square")
                Text(kind.rawValue)
            }
        }
    }
}

private struct ResourceKindBar: View {
    @Binding var selectedKinds: Set<TrafficFilter.ResourceKind>

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ResourceKindFilterButton(title: "All", isSelected: selectedKinds.isEmpty) {
                    selectedKinds.removeAll()
                }

                ForEach(TrafficFilter.ResourceKind.allCases) { kind in
                    ResourceKindFilterButton(title: kind.rawValue, isSelected: selectedKinds.contains(kind)) {
                        if selectedKinds.contains(kind) {
                            selectedKinds.remove(kind)
                        } else {
                            selectedKinds.insert(kind)
                        }
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }
}

private struct ResourceKindFilterButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.medium))
                .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
                .background(
                    isSelected ? Color.accentColor.opacity(0.18) : Color.primary.opacity(0.045),
                    in: RoundedRectangle(cornerRadius: 6)
                )
                .overlay {
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(isSelected ? Color.accentColor.opacity(0.55) : .clear, lineWidth: 1)
                }
        }
        .help(title == "All" ? "Show all resource types" : "Toggle \(title) resources")
    }
}

private struct MethodBadge: View {
    let method: String

    var body: some View {
        Text(method)
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15), in: RoundedRectangle(cornerRadius: 4))
    }

    private var color: Color {
        switch method {
        case "GET": return .blue
        case "POST": return .green
        case "PUT", "PATCH": return .orange
        case "DELETE": return .red
        case "CONNECT": return .purple
        default: return .secondary
        }
    }
}

private struct ResourceKindBadge: View {
    let kind: TrafficFilter.ResourceKind

    var body: some View {
        Text(kind.rawValue)
            .font(.system(.caption, design: .monospaced).weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.13), in: RoundedRectangle(cornerRadius: 4))
    }

    private var color: Color {
        switch kind {
        case .document: return .primary
        case .fetch: return .blue
        case .script: return .orange
        case .stylesheet: return .blue
        case .image: return .green
        case .media: return .red
        case .font: return .indigo
        case .websocket: return .purple
        case .other: return .secondary
        }
    }
}

private struct EmptyTrafficState: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.primary.opacity(0.055))
                    .frame(width: 62, height: 62)
                Image(systemName: state.isCapturing ? "dot.radiowaves.left.and.right" : "waveform.path.ecg.rectangle")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(state.isCapturing ? Color.green : Color.secondary)
            }

            VStack(spacing: 5) {
                Text(title)
                    .font(.title3.weight(.semibold))
                Text(message)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 430)
            }

            HStack(spacing: 8) {
                EmptyStatePill(title: state.systemProxyEnabled ? "Device routed" : "Device not routed", systemImage: "network")
                EmptyStatePill(title: state.caTrustInstalled ? "CA trusted" : "CA not trusted", systemImage: "seal")
                EmptyStatePill(title: "127.0.0.1:\(state.port)", systemImage: "number")
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .controlBackgroundColor))
    }

    private var title: String {
        if state.isCapturing, !state.systemProxyEnabled { return "Manual capture is running" }
        if state.isCapturing { return "Waiting for traffic" }
        return "No traffic captured"
    }

    private var message: String {
        if state.isCapturing, !state.systemProxyEnabled {
            return "Only clients configured to use the proxy will appear here. Switch to Device mode to route this Mac automatically."
        }
        if state.isCapturing, !state.caTrustInstalled {
            return "HTTP traffic should appear immediately. Trust the CA to inspect HTTPS traffic without certificate errors."
        }
        if state.isCapturing {
            return "Open an app or browser and make a request. New flows will appear as they start."
        }
        return "Start device capture to run the proxy and route this Mac through it."
    }
}

private struct EmptyFilterState: View {
    var body: some View {
        VStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.primary.opacity(0.055))
                    .frame(width: 56, height: 56)
                Image(systemName: "line.3.horizontal.decrease.circle")
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Text("No matching traffic")
                .font(.headline)
            Text("Clear or loosen the current filters.")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .controlBackgroundColor))
    }
}

private struct EmptyStatePill: View {
    let title: String
    let systemImage: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 6))
    }
}

private struct StatusBadge: View {
    let status: Int?
    let error: String?

    var body: some View {
        if let error {
            Text("ERR")
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .foregroundStyle(Color.red)
                .help(error)
        } else if let status {
            Text("\(status)")
                .font(.system(.callout, design: .monospaced).weight(.medium))
                .foregroundStyle(color(for: status))
        } else {
            Text("…")
                .foregroundStyle(.tertiary)
        }
    }

    private func color(for status: Int) -> Color {
        switch status {
        case 200..<300: return .green
        case 300..<400: return .blue
        case 400..<500: return .orange
        case 500..<600: return .red
        default: return .secondary
        }
    }
}
