import SwiftUI
import ReverseAPIProxy
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 0) {
            CaptureToolbar()
            HSplitView {
                TrafficListView()
                    .frame(minWidth: 600, maxHeight: .infinity)
                InspectorView()
                    .frame(minWidth: 460, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    Color(nsColor: .underPageBackgroundColor).opacity(0.75),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .task {
            await state.recoverStaleSystemProxyOnLaunch()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            state.restoreProxyBeforeExit()
        }
    }
}
