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
        .background(SidebarShortcutHandler(isSidebarVisible: $isSidebarVisible))
        .task {
            await state.recoverStaleSystemProxyOnLaunch()
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

private struct SidebarShortcutHandler: NSViewRepresentable {
    @Binding var isSidebarVisible: Bool

    func makeCoordinator() -> Coordinator {
        Coordinator(isSidebarVisible: $isSidebarVisible)
    }

    func makeNSView(context: Context) -> NSView {
        context.coordinator.installMonitor()
        return NSView(frame: .zero)
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.isSidebarVisible = $isSidebarVisible
    }

    final class Coordinator {
        var isSidebarVisible: Binding<Bool>
        private var monitor: Any?

        init(isSidebarVisible: Binding<Bool>) {
            self.isSidebarVisible = isSidebarVisible
        }

        deinit {
            if let monitor {
                NSEvent.removeMonitor(monitor)
            }
        }

        func installMonitor() {
            guard monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                guard let self else { return event }
                let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
                let togglesSidebar = event.charactersIgnoringModifiers?.lowercased() == "b" &&
                    (modifiers.contains(.command) || modifiers.contains(.control))
                guard togglesSidebar else { return event }
                isSidebarVisible.wrappedValue.toggle()
                return nil
            }
        }
    }
}
