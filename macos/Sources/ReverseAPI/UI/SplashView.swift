import SwiftUI

/// First-frame launch surface — shows the brand wordmark with a small
/// asterisk animation while the rest of the app finishes wiring up
/// (CA load, DB open, ProxyEngine init, font registration).
///
/// Visible for ~1.6s, then fades into the main `ContentView`. Plays the
/// same role as iOS's LaunchScreen.storyboard — a brand moment that
/// hides the brief "blank window" frame.
struct SplashView: View {
    /// Scale-in pop of the asterisk on first appear.
    @State private var asteriskScale: CGFloat = 0.55
    /// Continuous gentle wobble — the visible "movement" the user asked for.
    @State private var asteriskRotation: Double = -10
    /// Wordmark fades in slightly after the asterisk lands.
    @State private var wordmarkOpacity: Double = 0
    /// Wordmark slides in from the asterisk's right.
    @State private var wordmarkOffset: CGFloat = -18

    var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(spacing: 14) {
                Spacer()

                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("*")
                        .font(.fraunces(size: 96, weight: 600))
                        .foregroundStyle(Theme.brandPink)
                        .baselineOffset(-10)
                        .scaleEffect(asteriskScale, anchor: .center)
                        .rotationEffect(.degrees(asteriskRotation))
                    Text("rae")
                        .font(.fraunces(size: 76, weight: 600))
                        .foregroundStyle(Theme.textPrimary)
                        .opacity(wordmarkOpacity)
                        .offset(x: wordmarkOffset)
                }

                Spacer()

                Text("warming up")
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(Theme.textTertiary)
                    .tracking(2.0)
                    .textCase(.uppercase)
                    .padding(.bottom, 40)
            }
        }
        .onAppear {
            // Pop the asterisk in with a small overshoot, then start the
            // continuous wobble.
            withAnimation(.spring(response: 0.55, dampingFraction: 0.55)) {
                asteriskScale = 1.0
                asteriskRotation = 0
            }
            withAnimation(.easeOut(duration: 0.45).delay(0.25)) {
                wordmarkOpacity = 1
                wordmarkOffset = 0
            }
            // Continuous gentle wobble — never settles fully, so the eye
            // always reads it as alive.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
                withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                    asteriskRotation = 6
                }
            }
        }
    }
}
