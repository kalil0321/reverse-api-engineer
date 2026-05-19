import Foundation
import Crypto
import X509
import SwiftASN1
import Security

public enum CAStoreError: Error {
    case missingCertificateOnDisk
    case keychainWriteFailed(OSStatus)
    case keychainReadFailed(OSStatus)
    case invalidStoredPrivateKey
}

public final class CAStore: @unchecked Sendable {
    public let directory: URL
    public let certificateURL: URL

    private let keychainService = "app.reverseapi"
    private let keychainAccount = "ca.root-private-key"

    public init(applicationSupportURL: URL) throws {
        let root = applicationSupportURL.appendingPathComponent("ReverseAPI", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        self.directory = root
        self.certificateURL = root.appendingPathComponent("root.cer")
    }

    public func loadOrCreate() throws -> RootCertificate {
        if let existing = try? load() { return existing }
        return try createAndStore()
    }

    public func load() throws -> RootCertificate {
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
        try? FileManager.default.removeItem(at: certificateURL)
        try deletePrivateKey()
    }

    public func exists() -> Bool {
        guard FileManager.default.fileExists(atPath: certificateURL.path) else { return false }
        return (try? loadPrivateKeyPEM()) != nil
    }

    private func storePrivateKeyPEM(_ data: Data) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)

        var addQuery = query
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        guard status == errSecSuccess else { throw CAStoreError.keychainWriteFailed(status) }
    }

    private func loadPrivateKeyPEM() throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else {
            throw CAStoreError.keychainReadFailed(status)
        }
        return data
    }

    private func deletePrivateKey() throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        let status = SecItemDelete(query as CFDictionary)
        if status != errSecSuccess && status != errSecItemNotFound {
            throw CAStoreError.keychainWriteFailed(status)
        }
    }
}
