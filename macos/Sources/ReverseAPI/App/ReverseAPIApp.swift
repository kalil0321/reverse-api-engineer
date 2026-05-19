import SwiftUI

@main
struct ReverseAPIApp: App {
    @State private var session = AppSession.live()

    var body: some Scene {
        Window("ReverseAPI", id: "main") {
            switch session {
            case .ready(let state):
                ContentView()
                    .environment(state)
                    .frame(
                        minWidth: 1100,
                        maxWidth: .infinity,
                        minHeight: 700,
                        maxHeight: .infinity,
                        alignment: .topLeading
                    )
            case .failed(let error):
                BootFailureView(error: error)
                    .frame(minWidth: 500, minHeight: 300)
            }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}

enum AppSession {
    case ready(AppState)
    case failed(Error)

    @MainActor
    static func live() -> AppSession {
        do {
            return .ready(try AppState())
        } catch {
            return .failed(error)
        }
    }
}

struct BootFailureView: View {
    let error: Error

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.red)
            Text("ReverseAPI failed to start")
                .font(.title2)
                .bold()
            Text(String(describing: error))
                .font(.system(.body, design: .monospaced))
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .multilineTextAlignment(.center)
        }
        .padding(40)
    }
}
