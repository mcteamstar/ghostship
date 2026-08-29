# Contributing to Ghostship

## How this repo is meant to be consumed

**Start by cloning it.** The `spec-ops` composition and the six built-in
agent personas are a complete, working setup for OpenSpec-driven development.
If that covers your needs, you can run it as-is and pull upstream updates
whenever a new version ships.

**Fork it as soon as you start customising.** The moment you add an agent
persona, write a skill, build a new composition, or wire in an MCP server —
that configuration belongs to you. Fork `mcteamstar/ghostship` and own it.

This is the intended model, not a workaround. Your academy curriculum is as
much a part of your product as your codebase. It should live somewhere you
control, evolve at your pace, and be versioned alongside the rest of your
work. Keeping it in your own fork means you're never blocked by a PR review
cycle for your own operational changes, and you can cut your own releases on
your own schedule.

The `ghostship-capability` skill covers everything you need: adding agent
personas, skills, steering, orders, MCP servers, and building new
compositions from scratch.

## Choosing a fork visibility

**Private** — visible only to you and the people you explicitly invite.
Right for solo operators, small teams, or anyone whose academy configuration
is sensitive (persona prompts, internal MCP servers, or compositions that
encode internal architecture). Zero contribution path back upstream, but
that's fine — you're a consumer. Pull upstream patches on your own schedule.

**Internal** — visible to your whole organisation, but not the public.
On GitHub this is an internal repository (GitHub Enterprise/Teams) or a
private org repo shared across teams. Right for companies where multiple
teams use ghostship but the configuration is internal IP. You can run a
proper internal release cadence, let teams contribute their own compositions,
and still pull upstream improvements. Treat it like a public fork but
scoped to your org — with its own CONTRIBUTING guide for internal
contributors if you want one.

**Public** — open to the world, can send PRs upstream, can be listed in the
Known Forks table below. Right for consultancies, platforms, or products
built on ghostship where visibility is an asset. The upstream relationship
becomes a two-way street: you benefit from core improvements and can
contribute general-purpose fixes back. A good public fork signals to your
clients and the community that you're investing in the ecosystem.

All three are equally valid ways to run ghostship. The only thing that
changes is who can see your academy curriculum and whether you can
contribute back upstream.

> **Note:** GitHub's "internal" visibility is a GitHub Enterprise / Teams
> feature. If you don't have Enterprise, a private org repo shared with
> your teams achieves the same thing in practice.

## Maintaining your fork

A fork is only useful if it stays current. Upstream ships bug fixes,
security patches, and transport improvements — your fork should track them.

**Recommended approach:**
```bash
# Add upstream as a remote (one-time)
git remote add upstream https://github.com/mcteamstar/ghostship.git

# Pull upstream releases into your fork
git fetch upstream
git merge upstream/main   # or cherry-pick specific fixes
```

When a new ghostship release lands, check the changelog and pull in anything
that affects the transport, install scripts, or base crew image. Your
`academy/` and `crews/` customisations are isolated from those layers — a
routine upstream merge should be low-friction.

If you find a bug in the transport or core scripts while running your fork
against real workloads (it happens), see below for how to get that fix
back upstream.

## What belongs upstream (mcteamstar/ghostship)

Pull requests to this repo are welcome for things that are genuinely general:

- **Bug fixes** in the transport, install scripts, or base crew image —
  especially anything that affects correctness, security, or reliability.
  Regression tests required.
- **Transport improvements** — new MCP tools, protocol changes, performance
  fixes, anything that makes the core engine better for everyone.
- **Documentation fixes** — corrections, clarifications, missing steps.
- **New compositions or academy content** — only if they're broadly useful
  to the general ghostship user base and not tied to a specific product or
  organisation's tooling.

If you're unsure whether something is general-purpose enough, open an issue
or a draft PR to discuss before investing in the implementation.

## What stays in your fork

- Agent personas, skills, steering, and orders tailored to your organisation
  or product
- Compositions that wrap external products or services specific to your stack
- Any `academy/` or `crews/` content that wouldn't make sense without
  something particular to your environment

If your fork evolves general-purpose improvements alongside your
organisation-specific content — as often happens — extract the general
parts into a separate PR to upstream rather than sending everything at once.

## PR guidelines

- Open an issue or draft PR for discussion before significant transport
  changes — a short description of what and why is enough.
- Keep PRs focused. A bug fix and a new feature are two PRs.
- All existing tests must pass. Add tests for new behaviour.
- Commit messages follow the conventional commit style used in this repo
  (`fix:`, `feat:`, `chore:`, `docs:`, `test:`).
- For security-sensitive changes (auth, HMAC, path handling), include a note
  on what was verified and how.

## Known forks

If you've built something on ghostship and want to be listed here, open a PR
adding a line below.

| Fork | Description |
|:-----|:------------|
| — | — |
