# Dependency maintenance

The repository inventory is [config/dependencies.yaml](../config/dependencies.yaml). It records direct and inherited tools, images, Python packages, OS package groups, shared assets and CI actions. Each component names its authoritative declaration, upstream source, version policy, compatibility evidence and review state. Keep the declaration in its existing source file; the inventory points to it rather than replacing it.

Run these commands from the repository root:

```sh
python3 scripts/dependency_check.py validate
python3 scripts/dependency_check.py check
```

`validate` is offline. It reports dependencies missing from the inventory, declaration drift, invalid derived-component links and review metadata errors. `check` first validates the inventory, then makes bounded, read-only requests to upstream registries and release sources. It prints the declared constraint, available candidate, compatibility status, review age and lookup result. A failed lookup is unknown, not current; partial results remain visible and the command exits nonzero. No command changes a pin, rebuilds an image, modifies a running crew, publishes a report or schedules future work. Use `--include-prerelease` only when reviewing prerelease candidates.

## Version sources and what they mean

- Python packages come from `transport/requirements.txt`, `radar/requirements.txt` and the base-admission Containerfile. Exact pins and bounded ranges are kept as declared. A range is not an installed resolution.
- npm adapters and CLIs are installed by `crews/spec-ops/toolchains/*.sh`; OpenSpec is installed by its Containerfile. The Codex CLI is supplied by the Codex ACP adapter and must not be inventoried as a separately installed package.
- The KiroCrew base image is digest-pinned in the admission Containerfile, with a matching default in `transport/config.py`. Kiro CLI and base OS packages are inherited. Check the actual image before claiming installed versions.
- Python, Radar and Caddy images use their declared image tags. A tag is a candidate selector, not proof of an immutable image digest or installed package set.
- Node.js follows the Node 24 stream. The NodeSource setup script SHA-256 in the spec-ops Containerfile is an independent integrity check and must be updated only after reviewing the fetched script.
- Shared `.agents` content is cloned from a moving `main` branch by default. Its resolved commit and the generated OpenSpec skills need image inspection.
- APT package groups are unpinned and resolved by the repositories in the parent image. Their installed package versions remain unknown until an image is inspected.
- GitHub Actions use major-version refs. CI requests Python 3.12 and the runner resolves its patch version. Host Podman and podman-compose versions depend on the maintainer's machine.

The check distinguishes an upstream version that is **available** from one shown as **compatible**. Registry metadata cannot establish KiroCrew support. Only recorded integration evidence can change compatibility from unknown or unsupported.

## Example output

This deterministic fixture demonstrates an available update, an overdue review, unsupported and unknown compatibility, and a failed upstream lookup. Fixture values are examples, not current dependency recommendations. The command exits 1 because the fixture includes a failed lookup.

```text
$ python3 scripts/dependency_check.py check --root tests/fixtures/dependency-report --inventory tests/fixtures/dependency-report/config/dependencies.yaml --fixture-responses tests/fixtures/dependency-report/responses.json
Dependency review (2026-11-08)
Inventory validation: PASS (5 components)
Candidate policy: stable only (use --include-prerelease to include prereleases)
Available versions are candidates only; compatibility is recorded evidence, not inferred.
ID | DECLARED | UPSTREAM | COMPATIBILITY | REVIEW | RESULT
update-candidate | 1.0.0 [exact package constraint; installed unknown] | 1.2.0 | unknown | 0d | fixture registry response
overdue-review | ==1.0.0 [exact constraint; installed unknown] | 2.0.0 | unknown | 68d overdue | fixture registry response
unsupported | 2.5.0 [exact package constraint; installed unknown] | 2.5.0 | unsupported | 0d | fixture registry response
lookup-failure | ==0.1.0 [exact constraint; installed unknown] | unknown | unknown | 0d | LOOKUP FAILED: fixture timeout after 5s
manual-unknown | manual; installed unknown | unknown | unknown | 0d | no package-version lookup; inspect the installed image or host
Result: INCOMPLETE (one or more upstream lookups failed)
```

## Review cadence and outcomes

Review the inventory monthly and before every release. A review older than 30 days, or a missing date, is overdue. Check security advisories and upstream compatibility warnings as soon as they are found; do not wait for the monthly review.

For every component, record `last_reviewed`, `outcome`, `next_review` and `evidence` in `config/dependencies.yaml`. Use a dated evidence link or concise test/build reference. A deferral records why the current declaration remains, what evidence was considered and the next review date. A lookup failure, absent installed-version evidence or unsupported combination must remain explicitly unknown/unsupported rather than being marked current.

## Compatibility and upgrade checks

Before changing a declaration, review coupled components together. For ACP adapters, verify KiroCrew's supported adapter range, login/authentication, model discovery and a fresh-crew turn using the actual selected model. For a KiroCrew image change, inspect the Kiro CLI and re-check `seed_kiro_db.py` against the image's migration table. For OpenSpec, check the CLI against the generated skills. For Node.js, verify the NodeSource script checksum. For Python changes, run the affected transport or Radar tests. Rebuild the affected images, inspect their resolved component versions and verify a fresh crew adopts them.

Keep the previous reviewed declarations and image digest available for rollback. If an upgrade fails an acceptance check, restore the previous declaration and rebuild from it; do not deploy until the normal explicit deployment approval is recorded. See the [release checklist](../RELEASING.md#dependency-review-before-release).

## Initial finding

The Codex ACP adapter is known to expose a model catalogue that does not cover the model set advertised by KiroCrew. The inventory marks this combination unsupported pending an adapter/model compatibility check, model discovery and an actual-model fresh-crew smoke test. The current source pin is not evidence that the adapter has been rebuilt or that a fix is available.
