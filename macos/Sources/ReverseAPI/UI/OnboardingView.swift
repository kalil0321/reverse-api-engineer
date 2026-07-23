import SwiftUI

/// First-launch welcome sheet that walks the user through the three setup
/// steps the app needs to actually capture traffic: trusting the local CA,
/// routing the device through the proxy, and starting the capture loop.
///
/// Gated by `@AppStorage("hasCompletedOnboarding")` in ContentView. The
/// flag is flipped from the explicit "Get started" / "Skip for now"
/// buttons, NOT from `.onDismiss`, so closing the window before
/// acknowledging doesn't silently mark onboarding done.
struct OnboardingView: View {
    @Environment(AppState.self) private var state
    @Binding var hasCompletedOnboarding: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 32) {
            header
            steps
            Spacer(minLength: 0)
            footer
        }
        .padding(.horizontal, 40)
        .padding(.vertical, 36)
        .frame(width: 520, height: 560)
        .background(Theme.surface)
        .preferredColorScheme(.dark)
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                // Brand asterisk in pink — mirrors the `*` mark used in the
                // website header / app icon / hero. Drawn as a glyph (not an
                // SF Symbol) so the Fraunces shape carries through.
                Text("*")
                    .font(.fraunces(size: 38, weight: 400))
                    .foregroundStyle(Theme.brandPink)
                    .baselineOffset(-4)
                Text("rae")
                    .font(.fraunces(size: 30, weight: 400))
                    .foregroundStyle(Theme.textPrimary)
            }
            Text("Three quick steps to start intercepting and reverse-engineering API traffic on this Mac.")
                .font(.callout)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Steps

    private var steps: some View {
        VStack(alignment: .leading, spacing: 22) {
            OnboardingStep(
                number: 1,
                title: "Trust the local root certificate",
                description: "Lets rae decrypt HTTPS traffic from apps that trust the user keychain.",
                isComplete: state.caTrustInstalled,
                isWorking: state.isWorking && !state.caTrustInstalled,
                completedLabel: "Trusted",
                actionLabel: "Trust CA",
                action: { Task { await state.installCATrust() } }
            )
            OnboardingStep(
                number: 2,
                title: "Route this Mac through the proxy",
                description: "Toggles macOS HTTP and HTTPS proxies on every active network service.",
                isComplete: state.systemProxyEnabled,
                isWorking: state.isWorking && state.caTrustInstalled && !state.systemProxyEnabled,
                completedLabel: "Routed",
                actionLabel: "Enable proxy",
                action: { Task { await state.enableSystemProxy() } }
            )
            OnboardingStep(
                number: 3,
                title: "Start capturing traffic",
                description: "Open the apps you want to inspect — captured flows land in the table on the left.",
                isComplete: state.isCapturing,
                isWorking: state.isWorking && state.systemProxyEnabled && !state.isCapturing,
                completedLabel: "Capturing",
                actionLabel: "Start capture",
                action: { Task { await state.toggleCapture() } }
            )
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            Button {
                hasCompletedOnboarding = true
                dismiss()
            } label: {
                Text("Skip for now")
                    .font(.callout)
                    .foregroundStyle(Theme.textTertiary)
            }
            .buttonStyle(.plain)

            Spacer()

            Button {
                hasCompletedOnboarding = true
                dismiss()
            } label: {
                Text("Get started")
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(Theme.appBackground)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 9)
                    .background(Theme.textPrimary, in: Capsule())
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Step row

private struct OnboardingStep: View {
    let number: Int
    let title: String
    let description: String
    let isComplete: Bool
    let isWorking: Bool
    let completedLabel: String
    let actionLabel: String
    let action: () -> Void

    /// Completion color. Pulls from `Theme.mint` (the cream/ink palette's
    /// dark mint variant) so the three "Trusted / Routed / Capturing"
    /// pills read as soft status indicators rather than vivid success
    /// stamps. Centralised on `Theme.mint` so any future palette tweak
    /// lives in one place.
    private static let completedGreen = Theme.mint

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            indicator
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(description)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lineSpacing(2)
            }
            Spacer(minLength: 8)
            actionAffordance
        }
    }

    @ViewBuilder
    private var indicator: some View {
        if isComplete {
            Image(systemName: "checkmark")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Self.completedGreen)
                .frame(width: 20, height: 20)
        } else {
            Text("\(number)")
                .font(.system(size: 12, weight: .semibold).monospacedDigit())
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 20, height: 20)
        }
    }

    @ViewBuilder
    private var actionAffordance: some View {
        if isComplete {
            Text(completedLabel)
                .font(.caption.weight(.medium))
                .foregroundStyle(Self.completedGreen)
        } else if isWorking {
            ProgressView()
                .controlSize(.small)
                .tint(Theme.textTertiary)
        } else {
            Button(action: action) {
                Text(actionLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.appBackground)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Theme.textPrimary, in: Capsule())
            }
            .buttonStyle(.plain)
        }
    }
}
