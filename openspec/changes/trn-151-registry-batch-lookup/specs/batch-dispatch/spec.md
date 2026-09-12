# batch-dispatch — Delta Spec (trn-151-registry-batch-lookup)

Updates to the `batch-dispatch` capability.

## MODIFIED Requirements

### Requirement: Blocking batch pickup collects results for a task_ids list

The existing requirement is modified: `_find_batch_by_task_ids` SHALL match a batch when **all** provided `task_ids` are members of that batch's recorded task list (subset match), not only when the sets are identical. A superset of task IDs (caller passes more than the batch recorded) SHALL NOT match — the intent is to find the batch a subset belongs to, not to accept arbitrary over-specification.

#### Scenario: Batch lookup — subset match
- **WHEN** `pickup(task_ids=[id1, id2])` is called and a registered batch contains `[id1, id2, id3]`
- **THEN** the batch is found and returned (subset of batch task IDs matches)

#### Scenario: Batch lookup — exact match still works
- **WHEN** `pickup(task_ids=[id1, id2, id3])` is called and a registered batch contains exactly `[id1, id2, id3]`
- **THEN** the batch is found and returned

#### Scenario: Batch lookup — superset does not match
- **WHEN** `pickup(task_ids=[id1, id2, id3, id4])` is called and a registered batch contains only `[id1, id2, id3]`
- **THEN** no batch is returned (caller passed more IDs than the batch holds)

#### Scenario: Batch lookup — disjoint does not match
- **WHEN** `pickup(task_ids=[id_x, id_y])` is called and no batch contains either ID
- **THEN** no batch is returned
