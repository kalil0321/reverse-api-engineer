import Foundation
import Observation
import GRDB
import ReverseAPIProxy

@MainActor
@Observable
public final class FlowStore {
    public private(set) var flows: [CapturedFlow] = []
    public private(set) var isReady = false

    private let database: DatabaseQueue
    private var subscription: Task<Void, Never>?

    public init(databaseURL: URL) throws {
        let parent = databaseURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        var config = Configuration()
        config.label = "reverseapi.flows"
        self.database = try DatabaseQueue(path: databaseURL.path, configuration: config)
        try Self.migrate(database)
        try loadInitial()
        isReady = true
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

    public func clear() throws {
        try database.write { db in
            _ = try PersistedFlow.deleteAll(db)
        }
        flows.removeAll()
    }

    public func flow(id: UUID) -> CapturedFlow? {
        flows.first(where: { $0.id == id })
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
            flows[index] = flow
        } else {
            flows.insert(flow, at: 0)
        }
    }

    private func persist(_ flow: CapturedFlow) {
        let record: PersistedFlow
        do {
            record = try PersistedFlow(from: flow)
        } catch {
            return
        }
        Task.detached(priority: .utility) { [database] in
            try? await database.write { db in
                try record.save(db)
            }
        }
    }

    private func loadInitial() throws {
        let records = try database.read { db in
            try PersistedFlow
                .order(PersistedFlow.Columns.startedAt.desc)
                .limit(500)
                .fetchAll(db)
        }
        flows = records.compactMap { try? $0.toCapturedFlow() }
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
