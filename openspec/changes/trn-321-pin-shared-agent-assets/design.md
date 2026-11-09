# Design

## Context

`crews/spec-ops/Containerfile` runs `git clone --depth 1 --branch "${AGENTS_REF}"`, which accepts only branch and tag names. `AGENTS_REF` defaults to `main` and can be overridden through `machine.images.agents_ref` (`bin/lib/yaml_config.py`), passed as a build arg by `bin/lib/install_main.py`. `.agents` has one tag, `v1.0.0`, which predates the commit 0.12.1 was tested with.

## Goals / Non-Goals

**Goals:**
- Reproducible crew permissions for a given Ghostship release.

**Non-Goals:**
- Pinning the Codex CLI patch version bundled by codex-acp; tracked separately in the dependency inventory.
- Creating tags in the `.agents` repository.

## Decisions

- **Pin by full SHA, not tag.** A SHA needs no action in another repository and cannot be moved. Alternative considered: tag `.agents` and pin the tag. Rejected for now because tags are mutable and it couples a Ghostship release to a step in another repo.
- **Fetch instead of clone.** Replace the clone with `git init`, `git fetch --depth 1 origin "$AGENTS_REF"` and `git checkout FETCH_HEAD`. GitHub serves shallow fetches of reachable SHAs, and the same command works for branches and tags.
- **Record the resolved commit.** Write `git rev-parse HEAD` into a file in the image and set the label from the build arg; the dependency check reads the build arg and flags anything that is not 40 hex characters.

## Risks / Trade-offs

- [Upstream force-push removes the pinned commit] → The build fails loudly at fetch; bump the pin deliberately.
- [Maintainers forget to bump the pin for `.agents` improvements] → The monthly dependency review in `docs/dependencies.md` already lists this entry; the check reports the gap between pin and upstream main.
