//
//  FunctionView.swift
//  CalculatorSwiftUI
//
//  Created by Tarokh on 10/9/20.
//  Copyright © 2020 Tarokh. All rights reserved.
//

import SwiftUI

struct FunctionView: View {
    let tokens = CalculatorTokens.current
    
    // define some variables
    enum MathFunctions {
        case sinus, cosinus, tangens
        
        func string() -> String {
            switch self {
            case .sinus:
                return "sin"
            case .cosinus:
                return "cos"
            case .tangens:
                return "tan"
            }
        }
        
        func operation(_ input: Double) -> Double {
            switch self {
            case .sinus:
                return sin(input)
            case .cosinus:
                return cos(input)
            case .tangens:
                return tan(input)
            }
        }
    }

    var function: MathFunctions
    @Binding var state: CalculationState
    
    var body: some View {
        return Text(function.string())
            .font(tokens.keyFont.value)
            .foregroundColor(tokens.functionText.value)
            .frame(width: tokens.keySize, height: tokens.keySize)
            .background(tokens.functionColor.value.opacity(tokens.functionFillOpacity))
            .cornerRadius(tokens.keyCornerRadius)
            .shadow(color: tokens.functionColor.value.opacity(tokens.functionShadowOpacity),
                    radius: tokens.keyShadowRadius, x: 0, y: tokens.keyShadowY)
            .accessibilityIdentifier("key-\(function.string())")
            .onTapGesture {
                self.state.currentNumber = self.function.operation(self.state.currentNumber)
        }
    }
}
