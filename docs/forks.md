# Using, forking, or cloning Ghostship

## How this repo is meant to be consumed

**Start by cloning it.** The `spec-ops` composition and the six built-in
agent personas are a complete, working setup for OpenSpec-driven development.
If that covers your needs, you can run it as-is and pull upstream updates
whenever a new version ships.

**Fork or clone it as soon as you start customising.** The moment you add an
agent persona, write a skill, build a new composition, or wire in an MCP
server — that configuration belongs to you. Fork or clone
`mcteamstar/ghostship` and own it.

The `ghostship-capability` skill covers everything you need: adding agent personas, skills, steering, orders, MCP servers, and building new compositions from scratch.

## Fork or clone — and choosing a visibility

**A GitHub "Fork" of a public repo is always public.** There is no visibility
picker on GitHub's fork action — forking `mcteamstar/ghostship` produces
another public repo, full stop. If your academy configuration is sensitive
(persona prompts, internal MCP servers, compositions that encode internal
architecture), a real GitHub fork is the wrong mechanism regardless of who
you share it with afterwards.

For a private or internal copy, **clone it instead** — a plain `git clone`
(or GitHub's import tool at `github.com/new/import`, which does the same
thing for you) into a new repo you create with whatever visibility you want:

```bash
git clone --bare https://github.com/mcteamstar/ghostship.git
cd ghostship.git
git push --mirror <your-new-private-or-internal-repo-url>
```

A clone has no GitHub fork-network relationship — track upstream manually instead (see [Maintaining your fork or clone](#maintaining-your-fork-or-clone)).

**Private** — visible only to you and your invitees. Right for solo operators and small teams, or anyone whose configuration is sensitive. Always a clone, never a real GitHub fork.

**Internal** — visible to your organisation, not the public. Right for companies where the configuration is internal IP. Clone, not a fork. Pull upstream improvements on your own schedule.

**Public** — open to the world. Can be a real GitHub fork, can send PRs upstream, and can be listed in the [Known Forks](#known-forks) table. Right for consultancies or products built on ghostship where visibility is an asset.

## Maintaining your fork or clone

A fork or clone is only useful if it stays current. Upstream ships bug
fixes, security patches, and transport improvements — yours should track
them.

**Recommended approach:**
```bash
# Add upstream as a remote (one-time)
git remote add upstream https://github.com/mcteamstar/ghostship.git

# Pull upstream releases into your fork or clone
git fetch upstream
git merge upstream/main   # or cherry-pick specific fixes
```

When a new ghostship release lands, check the changelog and pull in anything
that affects the transport, install scripts, or base crew image. Your
`academy/` and `crews/` customisations are isolated from those layers — a
routine upstream merge should be low-friction.

If you find a bug in the transport or core scripts while running your fork
or clone against real workloads, see [CONTRIBUTING.md](../CONTRIBUTING.md)
for how to get that fix back upstream.

## Known forks

If you've built something public on ghostship and want to be listed here,
open a PR adding a line below. (Private and internal clones aren't listed
here — there's nothing to link to.)

| Fork | Description |
|:-----|:------------|
| — | — |
