import SwiftUI

struct AgentSettingsView: View {
    @Bindable var agent: AgentSession
    @Binding var isPresented: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 32) {
                    usageSection
                }
                .padding(.horizontal, 28)
                .padding(.vertical, 24)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(minWidth: 480, idealWidth: 540, minHeight: 360, idealHeight: 420)
        .background(Theme.surface)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("Settings")
                .font(.fraunces(size: 20, weight: 400))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Button {
                isPresented = false
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 22, height: 22)
                    .background(Theme.elevated, in: Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 24)
        .padding(.top, 18)
        .padding(.bottom, 14)
    }

    private var usageSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionLabel("Session usage")
            let usage = agent.sessionUsage
            if usage.numTurns == 0 {
                Text("No turns yet — stats appear after the first reply.")
                    .font(.caption)
                    .foregroundStyle(Theme.textTertiary)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    usageRow(label: "Input", value: usage.inputTokens.formatted(.number), unit: "tokens")
                    usageRow(label: "Output", value: usage.outputTokens.formatted(.number), unit: "tokens")
                    usageRow(label: "Cache read", value: usage.cacheReadInputTokens.formatted(.number), unit: "tokens")
                    usageRow(label: "Cache write", value: usage.cacheCreationInputTokens.formatted(.number), unit: "tokens")
                    Divider().background(Theme.border).padding(.vertical, 2)
                    usageRow(
                        label: "Cost",
                        value: usage.totalCostUsd.map { String(format: "$%.4f", $0) } ?? "—",
                        unit: "USD",
                        highlight: true
                    )
                    usageRow(label: "Duration", value: formattedDuration(usage.durationMs), unit: nil)
                    usageRow(label: "Turns", value: "\(usage.numTurns)", unit: nil)
                }
                if let model = usage.model {
                    Text("Last turn ran on \(model)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textTertiary)
                        .padding(.top, 4)
                }
            }
        }
    }

    private func usageRow(label: String, value: String, unit: String?, highlight: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
            Spacer()
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(value)
                    .font(.system(.callout, design: .monospaced).weight(highlight ? .semibold : .regular))
                    .foregroundStyle(highlight ? Theme.brandPink : Theme.textPrimary)
                    .monospacedDigit()
                if let unit {
                    Text(unit)
                        .font(.caption)
                        .foregroundStyle(Theme.textTertiary)
                }
            }
        }
    }

    private func formattedDuration(_ ms: Int) -> String {
        if ms < 1_000 { return "\(ms)" }
        let seconds = Double(ms) / 1_000
        if seconds < 60 { return String(format: "%.1fs", seconds) }
        let minutes = Int(seconds) / 60
        let remaining = Int(seconds) % 60
        return "\(minutes)m \(remaining)s"
    }

    private func sectionLabel(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 10, weight: .bold, design: .monospaced))
            .foregroundStyle(Theme.textTertiary)
            .tracking(0.8)
    }
}
