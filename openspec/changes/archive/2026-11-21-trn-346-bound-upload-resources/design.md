## Context

TRN-345 provides confined transfer helpers and stages archives and bundle checkouts before publishing them. Transport still reads the full HTTP body and builds the outer Podman tar in memory.

## Decisions

- Start with proposed defaults of 256 MiB per request, 1 GiB expanded per archive, and 100,000 archive members. Check representative transfers before finalizing these defaults and the separate bundle storage default. Expose positive integer overrides through the normal Transport configuration path.
- Reject oversized declared lengths early. Count actual bytes while streaming to a temporary file, including when length is absent. Keep memory bounded through the Podman tar handoff too. Use the staged file size to write the tar header without materializing its contents. Clean up host and crew staging on rejection, disconnect, or handoff failure.
- Count archive members during parsing and enforce output limits before and while writing extraction data. Keep the existing path checks and publish only after the staged archive passes all budget checks.
- Give each bundle operation a hard storage ceiling that applies while Git runs and covers its object database, temporary Git files, and the working tree. Confirm that the chosen enforcement mechanism works inside a rootless crew on both Linux and macOS Podman. A size check after Git exits cannot enforce the ceiling. If the mechanism is unavailable, fail safely before starting Git. Keep the existing destination until the bounded checkout succeeds.
- Map explicit budget breaches to HTTP 413. Keep ordinary storage failures, malformed input, and disconnects distinguishable from configured budget breaches.

## Trade-offs

Large legitimate transfers may need operator overrides. These limits apply per transfer. Aggregate quotas, concurrent transfer admission, and CPU or wall-clock budgets are outside this change.
