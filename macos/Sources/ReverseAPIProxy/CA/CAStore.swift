import Foundation
import Crypto
import X509
import SwiftASN1

public enum CAStoreError: Error {
    case missingCertificateOnDisk
    case missingPrivateKeyOnDisk
    case invalidStoredPrivateKey
    case certificateDeleteFailed(any Error)
    case privateKeyDeleteFailed(any Error)
    case privateKeyWriteFailed(any Error)
}

public final class CAStore: @unchecked Sendable {
    public let directory: URL
    public let certificateURL: URL
    public let privateKeyURL: URL

    public init(applicationSupportURL: URL) throws {
        let root = applicationSupportURL.appendingPathComponent("ReverseAPI", isDirectory: true)
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        self.directory = root
        self.certificateURL = root.appendingPathComponent("root.cer")
        self.privateKeyURL = root.appendingPathComponent("root-key.pem")
    }

    public func loadOrCreate() throws -> RootCertificate {
        if exists() {
            return try load()
        }
        return try createAndStore()
    }

    public func load() throws -> RootCertificate {
        guard FileManager.default.fileExists(atPath: certificateURL.path) else {
            throw CAStoreError.missingCertificateOnDisk
        }
        let derBytes = try Data(contentsOf: certificateURL)
        let certificate = try Certificate(derEncoded: Array(derBytes))
        let pemData = try loadPrivateKeyPEM()
        guard let pemString = String(data: pemData, encoding: .utf8) else {
            throw CAStoreError.invalidStoredPrivateKey
        }
        let privateKey = try Certificate.PrivateKey(pemEncoded: pemString)
        return RootCertificate(certificate: certificate, privateKey: privateKey)
    }

    public func createAndStore() throws -> RootCertificate {
        let root = try CertificateAuthority.generateRoot()
        try Data(try root.derBytes()).write(to: certificateURL, options: .atomic)
        let pem = try root.privateKey.serializeAsPEM().pemString
        try storePrivateKeyPEM(Data(pem.utf8))
        return root
    }

    public func reset() throws {
        let manager = FileManager.default
        if manager.fileExists(atPath: certificateURL.path) {
            do {
                try manager.removeItem(at: certificateURL)
            } catch {
                throw CAStoreError.certificateDeleteFailed(error)
            }
        }
        if manager.fileExists(atPath: privateKeyURL.path) {
            do {
                try manager.removeItem(at: privateKeyURL)
            } catch {
                throw CAStoreError.privateKeyDeleteFailed(error)
            }
        }
    }

    public func exists() -> Bool {
        guard FileManager.default.fileExists(atPath: certificateURL.path) else { return false }
        return FileManager.default.fileExists(atPath: privateKeyURL.path)
    }

    private func storePrivateKeyPEM(_ data: Data) throws {
        do {
            try data.write(to: privateKeyURL, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: privateKeyURL.path)
        } catch {
            throw CAStoreError.privateKeyWriteFailed(error)
        }
    }

    private func loadPrivateKeyPEM() throws -> Data {
        guard FileManager.default.fileExists(atPath: privateKeyURL.path) else {
            throw CAStoreError.missingPrivateKeyOnDisk
        }
        return try Data(contentsOf: privateKeyURL)
    }
}
