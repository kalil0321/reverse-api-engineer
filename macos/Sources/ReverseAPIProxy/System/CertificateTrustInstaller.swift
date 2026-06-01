import Foundation
import Security

public enum CertificateTrustError: Error {
    case invalidCertificate
    case addFailed(OSStatus)
    case trustFailed(OSStatus)
}

public final class CertificateTrustInstaller: Sendable {
    public init() {}

    public func install(derBytes: Data) throws {
        let cert = try secCertificate(from: derBytes)

        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecValueRef as String: cert,
        ]
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status != errSecSuccess && status != errSecDuplicateItem {
            throw CertificateTrustError.addFailed(status)
        }

        let trustSettings: [[String: Any]] = [[
            kSecTrustSettingsResult as String: SecTrustSettingsResult.trustRoot.rawValue
        ]]
        let trustStatus = SecTrustSettingsSetTrustSettings(cert, .user, trustSettings as CFArray)
        guard trustStatus == errSecSuccess else {
            throw CertificateTrustError.trustFailed(trustStatus)
        }
    }

    public func uninstall(derBytes: Data) throws {
        let cert = try secCertificate(from: derBytes)
        SecTrustSettingsRemoveTrustSettings(cert, .user)
        let removeQuery: [String: Any] = [
            kSecClass as String: kSecClassCertificate,
            kSecValueRef as String: cert,
        ]
        SecItemDelete(removeQuery as CFDictionary)
    }

    public func isInstalled(derBytes: Data) -> Bool {
        guard let cert = try? secCertificate(from: derBytes) else { return false }
        var settings: CFArray?
        let status = SecTrustSettingsCopyTrustSettings(cert, .user, &settings)
        guard status == errSecSuccess, let array = settings as? [[String: Any]] else {
            return false
        }
        for entry in array {
            if let raw = entry[kSecTrustSettingsResult as String] as? Int,
               raw == Int(SecTrustSettingsResult.trustRoot.rawValue) {
                return true
            }
        }
        return false
    }

    private func secCertificate(from derBytes: Data) throws -> SecCertificate {
        guard let cert = SecCertificateCreateWithData(nil, derBytes as CFData) else {
            throw CertificateTrustError.invalidCertificate
        }
        return cert
    }
}
