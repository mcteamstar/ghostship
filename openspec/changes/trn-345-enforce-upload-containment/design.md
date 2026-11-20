## Context

Transport validates a signed upload path in its own filesystem, while the destination mutation occurs inside a crew.

## Goals / Non-Goals

Enforce workspace containment for plain uploads, archive unpack, bundle clone, and forced replacement. Resource limits belong to TRN-346.

## Decisions

Enforce the boundary in the filesystem that performs the write. Ensure concurrent path changes cannot invalidate the check. Validate archive contents and the destination before applying mutations, including any removal for forced replacement. Preserve signed URL behavior and valid nested destinations.

## Risks / Trade-offs

Unsafe or ambiguous paths fail closed. Rejection must preserve existing destination data and clean up temporary staging.
