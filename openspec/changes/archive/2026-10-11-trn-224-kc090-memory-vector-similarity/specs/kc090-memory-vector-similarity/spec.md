## Purpose

Documents the operator-visible behavior change introduced by KiroCrew 0.9.0 where memory retrieval switches from recency ordering to vector-similarity ranking, and the one-time re-embedding pass that may occur on crews with accumulated memory.

## ADDED Requirements

### Requirement: Operator documentation for vector-similarity retrieval upgrade
The system SHALL include operator-facing documentation for the 0.9.0 upgrade
stating that memory retrieval now ranks by vector similarity rather than
recency. The documentation SHALL inform operators that:

- On a long-running crew with accumulated memory, the set of memories injected
  into a given turn may differ after the upgrade (different memories may
  surface compared to pre-upgrade behavior).
- The first start after upgrading to 0.9.0 on a crew with existing memory rows
  may trigger a one-time re-embedding pass to backfill vector representations,
  which can briefly delay startup on large memory stores.
- Fresh or ephemeral crews (e.g. spec-ops) that start with no prior memory are
  unaffected by both the retrieval-ranking change and the re-embedding pass.

#### Scenario: Upgrade documentation present in 0.9.0 release notes
- **WHEN** an operator reads the ghostship 0.9.0 upgrade or release notes
- **THEN** the notes include a section covering the recency-to-vector-similarity retrieval change, the one-time re-embedding pass on existing memory rows, and the fact that ephemeral crews are unaffected

#### Scenario: Documentation describes task-quality impact for long-running crews
- **WHEN** an operator reviews the upgrade notes before upgrading a long-running crew
- **THEN** the notes explicitly state that post-upgrade task behavior may shift on crews with accumulated memory, because a different set of memories may be selected for injection

#### Scenario: Documentation describes startup latency risk
- **WHEN** an operator reviews the upgrade notes before upgrading a large-memory crew
- **THEN** the notes explicitly state that the first startup after upgrade may be briefly delayed by the one-time re-embedding pass on existing memory rows

#### Scenario: Documentation confirms ephemeral crew safety
- **WHEN** an operator reviews the upgrade notes for an ephemeral spec-ops crew
- **THEN** the notes confirm that crews starting fresh with no accumulated memory are unaffected by both the retrieval-ranking change and the re-embedding pass

### Requirement: DB seed schema unaffected by vector-similarity upgrade
The ghostship DB seed (`seed_kiro_db.py`) SHALL continue to seed only the four
gateway-infrastructure tables: `auth_kv`, `history`, `migrations` (versions
0–5, resulting in `(6, 5)` for `COUNT(*), MAX(version)`), and `state`. The
seed SHALL NOT pre-create any `memories`, `lessons`, or embedding table — those
tables remain owned by the gateway's own first-start migration. Under KiroCrew
0.9.0+, the vector-similarity memory subsystem SHALL be fully provisioned by
gateway migration, not by the ghostship seed.

#### Scenario: Pristine 0.9.0 image seed contains no embedding table
- **WHEN** the pristine KiroCrew 0.9.0 base image is inspected before gateway first-start
- **THEN** the SQLite database contains no `memories`, `lessons`, or embedding-related table that ghostship would be expected to have pre-created

#### Scenario: Seed migration record matches expected baseline
- **WHEN** the ghostship-seeded SQLite database is inspected after image build
- **THEN** `SELECT COUNT(*), MAX(version) FROM migrations` returns `(6, 5)`, confirming the seed covers exactly migrations 0 through 5

#### Scenario: Gateway migration creates memory tables on first start
- **WHEN** a crew's gateway starts for the first time on a ghostship-seeded database
- **THEN** the gateway's own migration creates any memory, lessons, or embedding tables required for vector-similarity retrieval without ghostship intervention
