# Design

## Context

See proposal.md for motivation. The checker currently defaults to `config/dependencies.yaml` both when imported and when invoked with a custom repository root. Documentation links to that path. Inventory records also contain declaration paths such as `config/ghostship.yaml.example`; those are references to dependency declarations and remain valid after moving the inventory.

## Goals / Non-Goals

**Goals:** Keep the command's default behavior working from the checkout and from `--root`, while making the repository-wide inventory's ownership clear.

**Non-Goals:** Change inventory schema or contents, dependency extraction or reporting, review cadence, CLI options, or fixture layout. Do not relocate runtime configuration or declaration files.

## Decisions

### Put the inventory at repository root

Use `dependencies.yaml` at the repository root. It describes dependencies across Ghostship, so a root location communicates repository-wide scope. `config/` contains operator/runtime configuration, and `crews/` covers only one part of the project. A dedicated inventory directory would add hierarchy without a second related inventory.

### Resolve the default relative to the selected repository root

Keep `--inventory` as the explicit override. The default is `<root>/dependencies.yaml` for both the module default and command-line resolution, so `--root` continues to support isolated fixture repositories. Fixture data can remain under its existing `config/` subdirectory because it is an independent test fixture, not the production inventory location.

### Update maintained references, preserve historical evidence

Update current README, dependency guide, and release checklist links and instructions. Leave dated dependency review records and archived OpenSpec artifacts unchanged: they document the inventory's location at the time of review. Do not rewrite declaration paths inside the inventory unless an actual declaration file moves.

## Risks / Trade-offs

- A missed current reference could direct maintainers to a removed path → search maintained source/docs/tests for the old path and run the offline inventory validation and focused tests.
- Historical documents will still mention the former path → retain them as time-bound evidence and make the transition clear in current documentation.

## Migration Plan

Move the existing YAML without changing its contents, update the checker and maintained references, then run the inventory validation and dependency-check unit tests. Rollback restores the file to `config/` and reverts the default paths and links; no runtime service migration is involved.
