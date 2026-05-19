import XCTest
import X509
import SwiftASN1
@testable import ReverseAPIProxy

final class CertificateAuthorityTests: XCTestCase {
    func testGenerateRootIsSelfSigned() throws {
        let root = try CertificateAuthority.generateRoot()
        XCTAssertEqual(root.certificate.subject, root.certificate.issuer)
    }

    func testGenerateRootHasBasicConstraints() throws {
        let root = try CertificateAuthority.generateRoot()
        let bc = try root.certificate.extensions.basicConstraints
        guard case .some(.isCertificateAuthority) = bc else {
            XCTFail("Expected CA basic constraints, got \(String(describing: bc))")
            return
        }
    }

    func testRootPEMRoundtrips() throws {
        let root = try CertificateAuthority.generateRoot()
        let pem = try root.pem()
        XCTAssertTrue(pem.contains("-----BEGIN CERTIFICATE-----"))
        XCTAssertTrue(pem.contains("-----END CERTIFICATE-----"))
    }

    func testLoadRootFromPEM() throws {
        let root = try CertificateAuthority.generateRoot()
        let loaded = try CertificateAuthority.loadRoot(certificatePEM: try root.pem(), privateKeyPEM: try root.privateKeyPEM())
        XCTAssertEqual(try root.derBytes(), try loaded.derBytes())
        XCTAssertEqual(root.privateKey.publicKey, loaded.privateKey.publicKey)
    }

    func testRootCertificateStorePersistsAndReloadsRoot() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let store = RootCertificateStore(directory: directory)
        let first = try store.loadOrCreate()
        let second = try store.loadOrCreate()

        XCTAssertTrue(FileManager.default.fileExists(atPath: store.certificateURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: store.privateKeyURL.path))
        XCTAssertEqual(try first.derBytes(), try second.derBytes())
        XCTAssertEqual(first.privateKey.publicKey, second.privateKey.publicKey)
    }

    func testLeafCertificateFactoryProducesLeafForHost() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root)
        let materials = try await factory.materials(for: "example.com")
        XCTAssertNotNil(materials.certificate)
        XCTAssertNotNil(materials.privateKey)
    }

    func testLeafCertificateFactoryCachesPerHost() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root)
        let first = try await factory.materials(for: "example.com")
        let second = try await factory.materials(for: "example.com")
        XCTAssertEqual(try first.certificate.toDERBytes(), try second.certificate.toDERBytes())
    }
}
