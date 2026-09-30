import XCTest
@testable import CalculatorSwiftUI

final class CalculationRegressionTests: XCTestCase {
    func testAppendingDigitsPreservesExistingInputBehavior() {
        var state = CalculationState()
        state.appendNumber(2)
        state.appendNumber(3)
        XCTAssertEqual(state.currentNumber, 23)
        state.currentNumber = .pi
        state.appendNumber(7)
        XCTAssertEqual(state.currentNumber, 7)
    }

    func testExistingArithmeticAndNonfiniteResults() {
        XCTAssertEqual(ActionView.Action.plus.calculate(2, 3), 5)
        XCTAssertEqual(ActionView.Action.minus.calculate(2, 3), -1)
        XCTAssertEqual(ActionView.Action.multiply.calculate(2, 3), 6)
        XCTAssertEqual(ActionView.Action.divide.calculate(8, 2), 4)
        XCTAssertTrue(ActionView.Action.divide.calculate(1, 0)!.isInfinite)
        XCTAssertTrue(ActionView.Action.divide.calculate(0, 0)!.isNaN)
    }

    func testExistingTrigonometricFunctionsUseRadians() {
        XCTAssertEqual(FunctionView.MathFunctions.sinus.operation(0), 0)
        XCTAssertEqual(FunctionView.MathFunctions.cosinus.operation(0), 1)
        XCTAssertEqual(FunctionView.MathFunctions.tangens.operation(0), 0)
        XCTAssertEqual(FunctionView.MathFunctions.sinus.operation(.pi / 2), 1, accuracy: 0.000001)
    }
}
