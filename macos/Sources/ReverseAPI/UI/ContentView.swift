import SwiftUI
import ReverseAPIProxy

struct ContentView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 0) {
            CaptureToolbar()
            Divider()
            HSplitView {
                TrafficListView()
                    .frame(minWidth: 520)
                InspectorView()
                    .frame(minWidth: 420)
            }
        }
        .background(.background)
    }
}
