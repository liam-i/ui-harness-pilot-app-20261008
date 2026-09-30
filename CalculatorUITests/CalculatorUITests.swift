import XCTest

final class CalculatorUITests: XCTestCase {
    private struct Expectations: Decodable {
        struct Case: Decodable {
            let id: String
            let steps: [String]
            let expected_display: String
        }
        let cases: [Case]
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testApprovedCasesOnCurrentDevice() throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "app-expected", withExtension: "json"))
        let expected = try JSONDecoder().decode(Expectations.self, from: Data(contentsOf: url))
        XCTAssertEqual(expected.cases.count, 15)
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        let display = app.staticTexts["display"]
        XCTAssertTrue(display.waitForExistence(timeout: 5))
        let aliases = ["C": "clear", "+": "plus", "−": "minus", "×": "multiply", "÷": "divide", "=": "equal"]

        for item in expected.cases {
            XCTContext.runActivity(named: item.id) { activity in
                for step in item.steps {
                    switch step {
                    case "launch-clean": break
                    case "background":
                        XCUIDevice.shared.press(.home)
                        let background = expectation(for: NSPredicate { _, _ in
                            app.state == .runningBackground || app.state == .runningBackgroundSuspended
                        }, evaluatedWith: app)
                        wait(for: [background], timeout: 5)
                        XCTAssertTrue(app.state == .runningBackground || app.state == .runningBackgroundSuspended,
                                      "Unexpected application state: \(app.state.rawValue)")
                    case "foreground": app.activate()
                    default:
                        let key = app.descendants(matching: .any)["key-" + (aliases[step] ?? step)].firstMatch
                        XCTAssertTrue(key.waitForExistence(timeout: 5), "Missing key: \(step)")
                        XCTAssertTrue(key.isHittable, "Unreachable key: \(step)")
                        key.tap()
                    }
                }
                let value = expectation(for: NSPredicate(format: "label == %@", item.expected_display), evaluatedWith: display)
                wait(for: [value], timeout: 5)
                XCTAssertEqual(display.label, item.expected_display)
                XCTAssertTrue(app.windows.firstMatch.frame.contains(display.frame), "Display extends outside the window")
                let shot = XCTAttachment(screenshot: app.screenshot())
                shot.name = item.id
                shot.lifetime = .keepAlways
                activity.add(shot)
                print("CASE \(item.id) PASS display=\(display.label)")
            }
        }

        let ids = ["cos", "sin", "tan", "multiply", "7", "8", "9", "divide", "4", "5", "6", "plus", "1", "2", "3", "minus", "clear", "0", "π", "equal"]
        var frames: [CGRect] = []
        for id in ids {
            let key = app.descendants(matching: .any)["key-" + id].firstMatch
            XCTAssertTrue(key.isHittable)
            XCTAssertEqual(key.frame.width, 64, accuracy: 1)
            XCTAssertEqual(key.frame.height, 64, accuracy: 1)
            XCTAssertTrue(app.windows.firstMatch.frame.contains(key.frame))
            XCTAssertFalse(frames.contains { $0.intersects(key.frame) }, "Overlapping key: \(id)")
            frames.append(key.frame)
        }
        XCTAssertEqual(frames[4].minY - frames[0].maxY, 20, accuracy: 1)
        XCTAssertEqual(frames[0].minX, 32, accuracy: 1)
        XCTAssertEqual(app.windows.firstMatch.frame.maxX - frames[3].maxX, 32, accuracy: 1)
    }
}
