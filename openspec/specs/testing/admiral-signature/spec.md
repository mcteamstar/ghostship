# testing/admiral-signature Specification

## Purpose

Defines verification coverage for admiral signature behavior.

## Requirements

### Requirement: Admiral signature verifier has direct behavioral coverage
The test suite SHALL execute `verify-admiral-sig` against a valid signed message, a modified or invalidly signed message, and a message whose public key is missing. The tests SHALL verify the documented exit-code contract: 0 for a valid signature, 1 for invalid or malformed mail, and 2 when verification cannot proceed because the public key is absent.

#### Scenario: Valid signed message is accepted
- **WHEN** the verifier receives a message signed by the private key matching the mounted test public key
- **THEN** it exits with code 0

#### Scenario: Tampered message is rejected
- **WHEN** the verifier receives a message whose signed subject or body has been changed
- **THEN** it exits with code 1

#### Scenario: Malformed signature is rejected
- **WHEN** the verifier receives a malformed signature or malformed signed-message structure
- **THEN** it exits with code 1 and reports the message as invalid

#### Scenario: Missing public key is reported as unverifiable
- **WHEN** the verifier cannot read the public key after its retry window
- **THEN** it exits with code 2
