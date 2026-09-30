import SwiftUI

struct CalculatorTokens: Decodable {
    enum SemanticColor: String, Decodable {
        case blue = "SwiftUI.Color.blue"
        case green = "SwiftUI.Color.green"
        case gray = "SwiftUI.Color.gray"
        case white = "SwiftUI.Color.white"
        case black = "SwiftUI.Color.black"

        var value: Color {
            switch self {
            case .blue: return .blue
            case .green: return .green
            case .gray: return .gray
            case .white: return .white
            case .black: return .black
            }
        }
    }

    enum TextStyle: String, Decodable {
        case largeTitleBold = "largeTitle.bold"
        case titleBold = "title.bold"

        var value: Font {
            switch self {
            case .largeTitleBold: return .largeTitle.weight(.bold)
            case .titleBold: return .title.weight(.bold)
            }
        }
    }

    enum LoadError: Error, Equatable {
        case invalidValues
    }

    let units: String
    let screenInset: CGFloat
    let rowSpacing: CGFloat
    let keySize: CGFloat
    let keyCornerRadius: CGFloat
    let displayBottomPadding: CGFloat
    let displayLineLimit: Int
    let keyShadowRadius: CGFloat
    let keyShadowY: CGFloat
    let numberShadowOpacity: Double
    let functionShadowOpacity: Double
    let functionFillOpacity: Double
    let displayFont: TextStyle
    let keyFont: TextStyle
    let numberColor: SemanticColor
    let operatorColor: SemanticColor
    let functionColor: SemanticColor
    let numberText: SemanticColor
    let operatorText: SemanticColor
    let functionText: SemanticColor

    static let current: CalculatorTokens = {
        guard let url = Bundle.main.url(forResource: "tokens", withExtension: "json") else {
            fatalError("Missing approved calculator tokens in the application bundle")
        }
        do {
            return try load(from: url)
        } catch {
            fatalError("Invalid calculator tokens: \(error)")
        }
    }()

    static func load(from url: URL) throws -> CalculatorTokens {
        try decode(Data(contentsOf: url))
    }

    static func decode(_ data: Data) throws -> CalculatorTokens {
        let tokens = try JSONDecoder().decode(CalculatorTokens.self, from: data)
        let dimensions = [tokens.screenInset, tokens.rowSpacing, tokens.keySize,
                          tokens.keyCornerRadius, tokens.displayBottomPadding, tokens.keyShadowRadius]
        let opacities = [tokens.numberShadowOpacity, tokens.functionShadowOpacity, tokens.functionFillOpacity]
        guard tokens.units == "pt", tokens.keySize > 0, tokens.displayLineLimit > 0,
              dimensions.allSatisfy({ $0.isFinite && $0 >= 0 }), tokens.keyShadowY.isFinite,
              opacities.allSatisfy({ $0.isFinite && (0...1).contains($0) }) else {
            throw LoadError.invalidValues
        }
        return tokens
    }
}
