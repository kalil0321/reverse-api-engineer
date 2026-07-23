import SwiftUI

/// History view that lives inside the agent card. Lists every persisted
/// session sorted by recency, plus a "+" affordance at the top to create
/// a fresh one. Tapping a row opens that session in the timeline view.
struct SessionsListView: View {
    @Environment(AppState.self) private var state
    @State private var hoveredID: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            ThinDivider()
            list
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            Text("Sessions")
                .font(.fraunces(size: 18, weight: 600))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Button {
                state.agent.startNewSession()
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
            }
            .buttonStyle(.plain)
            .help("Start a new session")
        }
        .padding(.horizontal, 14)
        .frame(height: 44)
    }

    // MARK: - List body

    @ViewBuilder
    private var list: some View {
        if state.agent.store.sessions.isEmpty {
            emptyState
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(state.agent.store.sessions) { summary in
                        SessionRow(
                            summary: summary,
                            isHovered: hoveredID == summary.id
                        )
                        .onHover { hoveredID = $0 ? summary.id : nil }
                        .onTapGesture {
                            Task { await state.agent.openSession(id: summary.id) }
                        }
                        .contextMenu {
                            Button("Delete", role: .destructive) {
                                Task { await state.agent.deleteSession(id: summary.id) }
                            }
                        }
                    }
                }
                .padding(8)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(Theme.textTertiary)
            Text("No sessions yet")
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
            Text("Tap + to start a new conversation")
                .font(.caption)
                .foregroundStyle(Theme.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(20)
    }
}

// MARK: - Row

private struct SessionRow: View {
    let summary: AgentSessionSummary
    let isHovered: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(summary.title)
                .font(.callout)
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(2)
                .truncationMode(.tail)
            HStack(spacing: 6) {
                Text(relativeTime)
                    .font(.caption)
                    .foregroundStyle(Theme.textTertiary)
                if summary.messageCount > 0 {
                    Circle()
                        .fill(Theme.textTertiary.opacity(0.5))
                        .frame(width: 3, height: 3)
                    Text("\(summary.messageCount) message\(summary.messageCount == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(Theme.textTertiary)
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            isHovered ? Theme.elevated : Color.clear,
            in: RoundedRectangle(cornerRadius: 7)
        )
        .contentShape(Rectangle())
    }

    private var relativeTime: String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: summary.lastModifiedAt, relativeTo: Date())
    }
}
