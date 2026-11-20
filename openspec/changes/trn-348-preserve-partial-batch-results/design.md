## Context

The sequential batch loop records accepted IDs and has a partial finalizer. A gateway HTTP status error can bypass that finalizer.

## Goals / Non-Goals

Preserve accepted work and its IDs. Keep existing gateway recovery and single dispatch behavior.

## Decisions

Handle gateway refusals at the batch boundary using the existing partial result and registry contract. Keep sanitized error detail and the existing error shape if no spawn succeeded. Record only confirmed IDs and do not redispatch accepted tasks.

## Risks / Trade-offs

An ambiguous response can leave an unknown gateway outcome. Report only confirmed IDs and avoid claiming the refused or unconfirmed member completed.
