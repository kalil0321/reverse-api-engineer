import Foundation
import Observation
import GRDB
import ReverseAPIProxy

@MainActor
@Observable
public final class FlowStore {
    public private(set) var flows: [CapturedFlow] = []
    public private(set) var hostOptions: [String] = []
    public private(set) var methodOptions: [String] = []
    public private(set) var isReady = false

    private let database: DatabaseQueue
    private let generation = GenerationCounter()
    private let logger = AppLogger("app.flowstore")
    private var subscription: Task<Void, Never>?
    private var hostCounts: [String: Int] = [:]
    private var methodCounts: [String: Int] = [:]

    public init(databaseURL: URL) throws {
        let parent = databaseURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        var config = Configuration()
        config.label = "reverseapi.flows"
        self.database = try DatabaseQueue(path: databaseURL.path, configuration: config)
        try Self.migrate(database)
        Task { await loadInitial() }
    }

    public func subscribe(to bus: FlowBus) {
        subscription?.cancel()
        subscription = Task { @MainActor [weak self] in
            guard let self else { return }
            for await event in await bus.subscribe() {
                self.handle(event)
            }
        }
    }

    public func clear() async throws {
        let snapshot = generation.bump()
        let database = self.database
        try await Task.detached(priority: .userInitiated) {
            try await database.write { db in
                _ = try PersistedFlow.deleteAll(db)
            }
        }.value
        guard generation.value == snapshot else { return }
        flows.removeAll()
        resetFilterOptions()
    }

    public func flow(id: UUID) -> CapturedFlow? {
        flows.first(where: { $0.id == id })
    }

    /// Remove the given flows from both the in-memory list and the database.
    /// Safe to call with empty/unknown ids. Bails out without touching the
    /// in-memory list if the database delete fails so the two sides don't
    /// drift apart silently — caller can retry.
    public func delete(ids: Set<UUID>) async {
        guard !ids.isEmpty else { return }
        let snapshot = generation.bump()
        let database = self.database
        let stringIDs = ids.map { $0.uuidString }
        do {
            try await Task.detached(priority: .userInitiated) {
                try await database.write { db in
                    _ = try PersistedFlow
                        .filter(stringIDs.contains(PersistedFlow.Columns.id))
                        .deleteAll(db)
                }
            }.value
        } catch {
            logger.error("failed to delete \(ids.count) flow(s): \(error)")
            return
        }
        guard generation.value == snapshot else { return }
        let removed = flows.filter { ids.contains($0.id) }
        flows.removeAll { ids.contains($0.id) }
        for flow in removed {
            updateFilterOptions(removing: flow)
        }
    }

    private func handle(_ event: FlowEvent) {
        switch event {
        case .started(let flow):
            insertOrUpdate(flow)
        case .updated(let flow):
            insertOrUpdate(flow)
        case .finished(let flow):
            insertOrUpdate(flow)
            persist(flow)
        }
    }

    private func insertOrUpdate(_ flow: CapturedFlow) {
        if let index = flows.firstIndex(where: { $0.id == flow.id }) {
            updateFilterOptions(removing: flows[index])
            flows[index] = flow
        } else {
            flows.insert(flow, at: 0)
        }
        updateFilterOptions(adding: flow)
    }

    private func persist(_ flow: CapturedFlow) {
        let record: PersistedFlow
        do {
            record = try PersistedFlow(from: flow)
        } catch {
            logger.error("failed to encode flow \(flow.id) for persistence: \(error)")
            return
        }
        let snapshot = generation.value
        let counter = generation
        let logger = self.logger
        Task.detached(priority: .utility) { [database] in
            do {
                try await database.write { db in
                    guard counter.value == snapshot else { return }
                    try record.save(db)
                }
            } catch {
                logger.error("failed to persist flow \(record.id): \(error)")
            }
        }
    }

    private func loadInitial() async {
        do {
            let database = self.database
            let records = try await Task.detached(priority: .utility) {
                try database.read { db in
                    try PersistedFlow
                        .order(PersistedFlow.Columns.startedAt.desc)
                        .limit(500)
                        .fetchAll(db)
                }
            }.value

            var loaded: [CapturedFlow] = []
            for record in records {
                do {
                    loaded.append(try record.toCapturedFlow())
                } catch {
                    logger.error("failed to decode persisted flow \(record.id): \(error)")
                }
            }
            flows = loaded
            rebuildFilterOptions()
        } catch {
            logger.error("failed to load persisted flows: \(error)")
        }
        isReady = true
    }

    private func updateFilterOptions(adding flow: CapturedFlow) {
        increment(flow.host, in: &hostCounts)
        increment(flow.method, in: &methodCounts)
        publishFilterOptions()
    }

    private func updateFilterOptions(removing flow: CapturedFlow) {
        decrement(flow.host, in: &hostCounts)
        decrement(flow.method, in: &methodCounts)
        publishFilterOptions()
    }

    private func rebuildFilterOptions() {
        hostCounts = [:]
        methodCounts = [:]
        for flow in flows {
            increment(flow.host, in: &hostCounts)
            increment(flow.method, in: &methodCounts)
        }
        publishFilterOptions()
    }

    private func resetFilterOptions() {
        hostCounts = [:]
        methodCounts = [:]
        publishFilterOptions()
    }

    private func publishFilterOptions() {
        hostOptions = hostCounts.keys.sorted()
        methodOptions = methodCounts.keys.sorted()
    }

    private func increment(_ value: String, in counts: inout [String: Int]) {
        counts[value, default: 0] += 1
    }

    private func decrement(_ value: String, in counts: inout [String: Int]) {
        guard let count = counts[value] else { return }
        if count <= 1 {
            counts.removeValue(forKey: value)
        } else {
            counts[value] = count - 1
        }
    }

    private static func migrate(_ database: DatabaseQueue) throws {
        var migrator = DatabaseMigrator()
        migrator.registerMigration("v1") { db in
            try db.create(table: "flow") { t in
                t.column("id", .text).primaryKey()
                t.column("scheme", .text).notNull()
                t.column("method", .text).notNull()
                t.column("host", .text).notNull()
                t.column("port", .integer).notNull()
                t.column("path", .text).notNull()
                t.column("requestHeadersJSON", .blob).notNull()
                t.column("requestBody", .blob).notNull()
                t.column("responseStatus", .integer)
                t.column("responseHeadersJSON", .blob)
                t.column("responseBody", .blob).notNull()
                t.column("startedAt", .double).notNull()
                t.column("finishedAt", .double)
                t.column("errorMessage", .text)
            }
            try db.create(index: "idx_flow_host", on: "flow", columns: ["host"])
            try db.create(index: "idx_flow_startedAt", on: "flow", columns: ["startedAt"])
        }
        try migrator.migrate(database)
    }
}

final class GenerationCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var current: Int = 0

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return current
    }

    @discardableResult
    func bump() -> Int {
        lock.lock()
        defer { lock.unlock() }
        current += 1
        return current
    }
}
