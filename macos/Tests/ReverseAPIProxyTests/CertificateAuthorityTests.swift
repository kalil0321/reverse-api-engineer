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
