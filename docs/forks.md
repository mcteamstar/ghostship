# Using and forking Ghostship

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
work. The `ghostship-capability` skill covers everything you need: adding
agent personas, skills, steering, orders, MCP servers, and building new
compositions from scratch.

## Choosing a fork visibility

**Private** — visible only to you and the people you explicitly invite.
Right for solo operators, small teams, or anyone whose academy configuration
is sensitive (persona prompts, internal MCP servers, or compositions that
encode internal architecture). Zero contribution path back upstream, but
that's fine — you're a consumer. Pull upstream patches on your own schedule.

**Internal** — visible to your whole organisation, but not the public.
Right for companies where multiple teams use ghostship but the configuration
is internal IP. You can run a proper internal release cadence, let teams
contribute their own compositions, and still pull upstream improvements.
Treat it like a public fork but scoped to your org.

**Public** — open to the world, can send PRs upstream, can be listed in the
[Known Forks](#known-forks) table. Right for consultancies, platforms, or
products built on ghostship where visibility is an asset. The upstream
relationship becomes a two-way street: you benefit from core improvements
and can contribute general-purpose fixes back.

All three are equally valid ways to run ghostship. The only thing that
changes is who can see your academy curriculum and whether you can
contribute back upstream.

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
against real workloads, see [CONTRIBUTING.md](../CONTRIBUTING.md) for how
to get that fix back upstream.

## Known forks

If you've built something on ghostship and want to be listed here, open a PR
adding a line below.

| Fork | Description |
|:-----|:------------|
| — | — |
