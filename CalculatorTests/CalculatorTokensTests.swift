import XCTest
import CryptoKit
@testable import CalculatorSwiftUI

final class CalculatorTokensTests: XCTestCase {
    private func fixtureURL() throws -> URL {
        try XCTUnwrap(Bundle(for: Self.self).url(forResource: "approved-tokens", withExtension: "json"))
    }

    private func input(updating values: [String: Any] = [:], removing key: String? = nil) throws -> Data {
        let data = try Data(contentsOf: fixtureURL())
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        values.forEach { object[$0.key] = $0.value }
        if let key = key { object.removeValue(forKey: key) }
        return try JSONSerialization.data(withJSONObject: object)
    }

    func testApplicationBundleContainsTheFixedApprovedResource() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "tokens", withExtension: "json"))
        let data = try Data(contentsOf: url)
        let hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hash, "08f7649f3fc24f1f5f9845162eaef7a95169e0833cc8e35da3fc8ef49aff743d")
        XCTAssertLessThanOrEqual(data.count, 16 * 1024)
        XCTAssertEqual(CalculatorTokens.current.keySize, 64)
        XCTAssertEqual(CalculatorTokens.current.numberColor, .blue)
    }

    func testLoadReadsTheApprovedFile() throws {
        let tokens = try CalculatorTokens.load(from: fixtureURL())
        XCTAssertEqual(tokens.screenInset, 32)
        XCTAssertEqual(tokens.keySize, 64)
        XCTAssertEqual(tokens.displayLineLimit, 3)
        XCTAssertEqual(tokens.numberColor, .blue)
        XCTAssertEqual(tokens.keyFont, .titleBold)
    }

    func testDecodeUsesSuppliedValuesInsteadOfFixedConstants() throws {
        let tokens = try CalculatorTokens.decode(input(updating: ["screenInset": 28, "keySize": 72, "numberColor": "SwiftUI.Color.black"]))
        XCTAssertEqual(tokens.screenInset, 28)
        XCTAssertEqual(tokens.keySize, 72)
        XCTAssertEqual(tokens.numberColor, .black)
    }

    func testMissingRequiredFieldIsRejected() throws {
        XCTAssertThrowsError(try CalculatorTokens.decode(input(removing: "keySize"))) { error in
            guard case DecodingError.keyNotFound(let key, _) = error else {
                return XCTFail("Expected missing-field rejection, got \(error)")
            }
            XCTAssertEqual(key.stringValue, "keySize")
        }
    }

    func testMalformedJSONAndUnknownSemanticColorAreRejected() throws {
        for data in [Data("{".utf8), try input(updating: ["numberColor": "unsupported-color"]) ] {
            XCTAssertThrowsError(try CalculatorTokens.decode(data)) { error in
                XCTAssertTrue(error is DecodingError, "Expected decoding rejection, got \(error)")
            }
        }
    }

    func testInvalidLayoutUnitsAndOpacityAreRejected() throws {
        let updates: [[String: Any]] = [["keySize": 0], ["units": "px"], ["numberShadowOpacity": 1.1]]
        for update in updates {
            XCTAssertThrowsError(try CalculatorTokens.decode(input(updating: update))) { error in
                XCTAssertEqual(error as? CalculatorTokens.LoadError, .invalidValues)
            }
        }
    }

    func testMissingResourceReportsTheReadFailure() throws {
        let missing = try fixtureURL().deletingLastPathComponent().appendingPathComponent("missing-token-resource.json")
        XCTAssertThrowsError(try CalculatorTokens.load(from: missing)) { error in
            let value = error as NSError
            XCTAssertEqual(value.domain, NSCocoaErrorDomain)
            XCTAssertEqual(value.code, NSFileReadNoSuchFileError)
        }
    }
}
