# Calculator UI contract

## Purpose
Preserve the previously accepted calculator main-screen design within the explicitly reviewed limited trial.

## Requirements

### Requirement: Consume the approved runtime tokens
The application SHALL load UI-CALCULATOR/U001 tokens from its application bundle without changing the approved resource bytes, existing decoding validation or public API.

#### Scenario: Approved resource is present
- **WHEN** the existing calculator starts and its token tests run
- **THEN** the bundled resource matches SHA-256 08f7649f3fc24f1f5f9845162eaef7a95169e0833cc8e35da3fc8ef49aff743d and remains at most 16KiB

### Requirement: Retain the accepted initial screen
The initial main screen SHALL retain the accepted four-column five-row keyboard and 0.00 display on the two original trial simulator sizes under portrait, light, English and default text settings.

#### Scenario: Initial screen on the approved sizes
- **WHEN** the application starts on each original trial simulator
- **THEN** labels and controls are visible without overlap or safe-area clipping, subject to the original approved platform rendering differences
