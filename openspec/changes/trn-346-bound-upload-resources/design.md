## Context

Transport currently materializes the request before staging it. Archive unpack and bundle checkout have different expansion behavior.

## Decisions

- Propose 256 MiB per request, 1 GiB expanded per archive, and 100,000 archive members. Expose positive integer overrides through the normal Transport configuration path. Review these defaults against representative existing bundles before implementation.
- Reject an oversized declared length early and count actual bytes while reading, including when length is absent. Use bounded staging and remove partial data on failure or disconnect.
- Enforce archive limits before publishing destination output. Stage bundle checkout with an independent storage budget or equivalent enforceable bound, including forced replacement. Preserve the old destination if a limit is exceeded.
- TRN-345 owns path containment. This change owns resource limits. Per-crew quotas and download limits are outside this change.

## Trade-offs

Large legitimate transfers may need operator overrides. Avoid metadata-only accounting where it cannot bound actual output.
