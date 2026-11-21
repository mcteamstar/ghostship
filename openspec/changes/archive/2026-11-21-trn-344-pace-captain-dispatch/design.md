## Context

The shared check-in prompt requires one dispatch. Indy and Sweepy call for multiple independent reviewers. Existing intent markers and memory admission signals already support deferral and reconciliation.

## Decisions

- Separate the decision to dispatch from the number of eligible tasks. Prefer one task as the default. An order may authorize several starts during one check-in, with earlier tasks allowed to keep running.
- Submit starts sequentially and reconcile each admission before proceeding. Pace successive starts so agents can initialize. Use existing memory admission and deferral signals without introducing a universal delay or a new pressure threshold.
- For Indy and Sweepy, concurrent reviews means admitted review tasks may execute concurrently; Raven starts each work item sequentially and confirms its task ID before proceeding.
- Stop issuing new starts for that check-in when memory admission defers a spawn. Keep unfinished intents for the next cycle and preserve existing sustained pressure escalation.
- Reconcile by logical task identity and confirmed gateway task ID before retrying. For review orders use the reviewer track and shard, so same-persona roles remain distinct. An uncertain outcome requires reconciliation before retry.
- Align the common prompt and all built-in orders. Indy counts and shard configuration stay as they are.
