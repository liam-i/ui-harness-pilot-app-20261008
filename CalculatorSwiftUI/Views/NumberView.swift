//
//  NumberView.swift
//  CalculatorSwiftUI
//
//  Created by Tarokh on 10/9/20.
//  Copyright © 2020 Tarokh. All rights reserved.
//

import SwiftUI

struct NumberView: View {
    let tokens = CalculatorTokens.current
    
    // define some variables
    let number: Double
    var numberString: String {
        if number == Double.pi {
            return "π"
        }
        else if number == .myNumber {
            return "N"
        }
        return String(Int(number))
    }
    @Binding var state: CalculationState
    
    var body: some View {
        Text(numberString)
            .font(tokens.keyFont.value)
            .foregroundColor(tokens.numberText.value)
            .frame(width: tokens.keySize, height: tokens.keySize)
            .background(tokens.numberColor.value)
            .cornerRadius(tokens.keyCornerRadius)
            .shadow(color: tokens.numberColor.value.opacity(tokens.numberShadowOpacity),
                    radius: tokens.keyShadowRadius, x: 0, y: tokens.keyShadowY)
            .accessibilityIdentifier("key-\(numberString)")
            .onTapGesture {
                self.state.appendNumber(self.number)
        }
    }
}

extension Double {
    static let myNumber: Double = 1.2345
}
