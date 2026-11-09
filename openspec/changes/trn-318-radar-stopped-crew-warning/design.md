# Design

## Context

The fleet payload reports gateway health separately from crew status. Stopped crews naturally report the gateway as unhealthy, and the table currently renders that as a warning.

## Goals / Non-Goals

**Goals:** Make the warning actionable while retaining existing fleet status and health data.

**Non-Goals:** Change backend health reporting or hide warnings for running crews.

## Decisions

Use the status already provided to the row builder to suppress the gateway warning for `stopped`. Continue to render the warning for an unhealthy non-stopped crew. A local implementation already follows this approach and should be checked against the scenarios before completion.

Sort each existing running and inactive section by `created_at`, newest first, when no Last Task sort is selected. Missing or invalid creation times appear after valid timestamps. Preserve the Last Task sort control and section grouping.

## Risks / Trade-offs

- Additional non-running states may require their own presentation later; preserve their existing warning behaviour for now.
