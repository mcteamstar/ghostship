## MODIFIED Requirements

### Requirement: _steer_captain_checkin classifies errors by HTTP status code

Captain SHALL use structured gateway outcomes for continuation. A bare HTTP 400 SHALL NOT trigger another write. A busy outcome SHALL preserve the tracked task ID.

#### Scenario: 400 on /continue path triggers follow-up steer
- **WHEN** continuation returns HTTP 400
- **THEN** Captain starts recovery only if the response confirms a missing session or restore failure; otherwise it surfaces the rejection

#### Scenario: Continuation acceptance is unknown
- **WHEN** Captain cannot establish whether a continuation or replacement spawn was accepted
- **THEN** Captain adopts an existing task ID only when unique correlation identifies that attempt
- **AND** Captain exposes a hold to the operator without replaying the request when correlation is inconclusive
