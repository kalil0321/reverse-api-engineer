import Foundation

/// Resolves where to find the Python interpreter + `rae_agent` package
/// at launch time. There are three supported modes:
///
/// 1. **Bundled (production)** — the `.app` ships a self-contained
///    Python runtime at `Contents/Resources/agent-runtime/`. The interpreter
///    there has `rae-agent` and its dependencies installed in its
///    site-packages. The user installs the app and never touches Python.
///
/// 2. **Dev (`swift run`)** — the executable lives in
///    `<repo>/macos/.build/.../rae`. We walk up to find the repo root,
///    use `<repo>/.venv/bin/python3`, and rely on `rae-agent` being
///    installed in that venv (either editable via `uv pip install -e backend/`
///    or a regular install).
///
/// 3. **Fallback** — `/usr/bin/env python3` with no PYTHONPATH. Will only
///    work if the user has installed `rae-agent` globally. Mostly useful
///    so the error message is helpful, since the sidecar will fail with a
///    clear `ModuleNotFoundError`.
struct AgentRuntime {
    var executablePath: String
    var arguments: [String]
    var pythonPath: [String]
    var origin: Origin

    enum Origin: String {
        case bundled
        case dev
        case fallback
    }

    /// Returns the best runtime for the current process. Caller should pass
    /// the SwiftPM-style executable URL via `Bundle.main` so prod and dev
    /// resolve correctly.
    static func resolve(
        bundle: Bundle = .main,
        executableArgv0: String = CommandLine.arguments[0]
    ) -> AgentRuntime {
        if let bundled = bundledRuntime(in: bundle) {
            return bundled
        }
        if let dev = devRuntime(argv0: executableArgv0) {
            return dev
        }
        return AgentRuntime(
            executablePath: "/usr/bin/env",
            arguments: ["python3", "-m", "rae_agent.server"],
            pythonPath: [],
            origin: .fallback
        )
    }

    private static func bundledRuntime(in bundle: Bundle) -> AgentRuntime? {
        guard let resources = bundle.resourceURL else { return nil }
        let python = resources.appendingPathComponent("agent-runtime/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: python.path) else { return nil }
        return AgentRuntime(
            executablePath: python.path,
            arguments: ["-m", "rae_agent.server"],
            pythonPath: [],
            origin: .bundled
        )
    }

    private static func devRuntime(argv0: String) -> AgentRuntime? {
        guard let repoRoot = findRepoRoot(startingFrom: argv0) else { return nil }
        let venvPython = repoRoot.appendingPathComponent(".venv/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: venvPython.path) else { return nil }
        let backend = repoRoot.appendingPathComponent("backend").path
        return AgentRuntime(
            executablePath: venvPython.path,
            arguments: ["-m", "rae_agent.server"],
            pythonPath: [backend],
            origin: .dev
        )
    }

    /// Walks up from the executable looking for `backend/rae_agent/__init__.py`.
    /// Capped at 10 levels so we never wander out of the repo on weird paths.
    private static func findRepoRoot(startingFrom argv0: String) -> URL? {
        let fm = FileManager.default
        var dir = URL(fileURLWithPath: argv0).deletingLastPathComponent()
        for _ in 0..<10 {
            let marker = dir.appendingPathComponent("backend/rae_agent/__init__.py")
            if fm.fileExists(atPath: marker.path) {
                return dir
            }
            let parent = dir.deletingLastPathComponent()
            if parent == dir { break }
            dir = parent
        }
        return nil
    }
}
