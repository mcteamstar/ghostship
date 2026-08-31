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

## Choosing a visibility

**A GitHub "Fork" of a public repo is always public.** There is no visibility
picker on GitHub's fork action — forking `mcteamstar/ghostship` produces
another public repo, full stop. If your academy configuration is sensitive
(persona prompts, internal MCP servers, compositions that encode internal
architecture), a real fork is the wrong mechanism regardless of who you
share it with afterwards.

To get a private or internal copy instead, don't fork — **import or mirror
it**:

```bash
# Option A: GitHub's import tool (github.com/new/import) — paste this repo's
# clone URL, choose your visibility, GitHub clones the full history for you.

# Option B: manual bare mirror
git clone --bare https://github.com/mcteamstar/ghostship.git
cd ghostship.git
git push --mirror <your-new-private-or-internal-repo-url>
```

Either way this is a plain copy, not a GitHub "fork" — there's no
fork-network relationship, so you lose the built-in "compare across forks"
PR UI back to upstream. Track upstream manually instead (see
[Maintaining your fork](#maintaining-your-fork) below — the remote-based
workflow there works identically whether your copy is a real fork or an
imported mirror).

**Private** — visible only to you and the people you explicitly invite.
Right for solo operators, small teams, or anyone whose academy configuration
is sensitive. Zero contribution path back upstream via GitHub's PR UI, but
that's fine — you're a consumer. Pull upstream patches on your own schedule.

**Internal** — visible to your whole organisation, but not the public.
Right for companies where multiple teams use ghostship but the configuration
is internal IP. You can run a proper internal release cadence, let teams
contribute their own compositions, and still pull upstream improvements.
Treat it like a public fork but scoped to your org.

**Public** — open to the world. This one *can* be a real GitHub fork, can
send PRs upstream, and can be listed in the [Known Forks](#known-forks)
table. Right for consultancies, platforms, or products built on ghostship
where visibility is an asset. The upstream relationship becomes a two-way
street: you benefit from core improvements and can contribute general-purpose
fixes back.

All three are equally valid ways to run ghostship. What changes is who can
see your academy curriculum, whether you can contribute back upstream
through GitHub's native PR flow, and — for private/internal — whether you're
using a real fork or an imported mirror to get there.

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
