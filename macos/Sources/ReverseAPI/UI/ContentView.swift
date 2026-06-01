import SwiftUI
import ReverseAPIProxy
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var state
    @Binding var isSidebarVisible: Bool

    var body: some View {
        HStack(spacing: 0) {
            if isSidebarVisible {
                CaptureToolbar(isSidebarVisible: $isSidebarVisible)
                    .frame(width: 312)
                Divider()
            } else {
                CollapsedSidebarRail(isSidebarVisible: $isSidebarVisible)
                Divider()
            }

            HSplitView {
                TrafficListView()
                    .frame(minWidth: 600, maxHeight: .infinity)
                InspectorView()
                    .frame(minWidth: 460, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(nsColor: .windowBackgroundColor))
        .task {
            await state.recoverStaleSystemProxyOnLaunch()
        }
        .onReceive(NotificationCenter.default.publisher(for: .toggleRaeSidebar)) { _ in
            isSidebarVisible.toggle()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            state.restoreProxyBeforeExit()
        }
    }
}

private struct CollapsedSidebarRail: View {
    @Binding var isSidebarVisible: Bool

    var body: some View {
        VStack(spacing: 14) {
            Button {
                isSidebarVisible = true
            } label: {
                Image(systemName: "sidebar.left")
                    .font(.system(size: 16, weight: .medium))
                    .frame(width: 30, height: 30)
            }
            .buttonStyle(.plain)
            .help("Show sidebar")

            Image(systemName: "waveform.path.ecg")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Color.accentColor)

            Spacer()
        }
        .padding(.top, 14)
        .frame(minWidth: 48, idealWidth: 48, maxWidth: 48, maxHeight: .infinity)
        .background(Color(nsColor: .controlBackgroundColor))
    }
}
