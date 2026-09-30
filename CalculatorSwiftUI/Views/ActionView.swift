//
//  ActionView.swift
//  CalculatorSwiftUI
//
//  Created by Tarokh on 10/9/20.
//  Copyright © 2020 Tarokh. All rights reserved.
//

import SwiftUI

struct ActionView: View {
    let tokens = CalculatorTokens.current
    
    // define some variables
    enum Action {
        case equal, clear, plus, minus, multiply, divide
        
        func image() -> Image {
            switch self {
            case .equal:
                return Image(systemName: "equal")
            case .clear:
                return Image(systemName: "xmark.circle")
            case .plus:
                return Image(systemName: "plus")
            case .minus:
                return Image(systemName: "minus")
            case .multiply:
                return Image(systemName: "multiply")
            case .divide:
                return Image(systemName: "divide")
            }
        }
        
        func calculate(_ input1: Double, _ input2: Double) -> Double? {
            switch self {
            case .plus:
                return input1 + input2
            case .minus:
                return input1 - input2
            case .multiply:
                return input1 * input2
            case .divide:
                return input1 / input2
            default:
                return nil
            }
        }
    }
    
    let action: Action
    @Binding var state: CalculationState
    
    var body: some View {
        action.image()
            .font(tokens.keyFont.value)
            .foregroundColor(tokens.operatorText.value)
            .frame(width: tokens.keySize, height: tokens.keySize)
            .background(tokens.operatorColor.value)
            .cornerRadius(tokens.keyCornerRadius)
            .shadow(color: tokens.operatorColor.value.opacity(tokens.numberShadowOpacity),
                    radius: tokens.keyShadowRadius, x: 0, y: tokens.keyShadowY)
            .accessibilityIdentifier("key-\(action)")
            .onTapGesture {
                self.tapped()
        }
    }
    
    // define some functions
    private func tapped() {
        switch action {
        case .clear:
            state.currentNumber = 0
            state.storedNumber = nil
            state.storedAction = nil
            break
        case .equal:
            guard let storedAction = state.storedAction else {return}
            guard let storedNumber = state.storedNumber else {return}
            guard let result = storedAction.calculate(storedNumber, state.currentNumber) else {return}
            state.currentNumber = result
            state.storedNumber = nil
            state.storedAction = nil
            break
        default:
            state.storedNumber = state.currentNumber
            state.currentNumber = 0
            state.storedAction = action
            break
        }
    }
}
