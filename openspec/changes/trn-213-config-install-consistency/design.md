# Design

See `proposal.md` for motivation.

## Context

`scripts/install.sh` generates a `compose.yml` for the `ga-transport` service at install
time. That file is the sole mechanism by which the operator's shell environment reaches
the transport's `Config.from_env()`. Any env var that `install.sh` does not write into
the `environment:` block, or whose related host path it does not mount as a volume, is
silently inaccessible at runtime.

As of `ee0b3b8` the current state is:

| Var | config.py? | compose env? | volume? | Net effect |
|---|---|---|---|---|
| `GA_PREWARM_ENABLED` | ✓ | ✗ | n/a | setting ignored at runtime |
| `GA_PREWARM_TTL_SECS` | ✓ | ✗ | n/a | setting ignored at runtime |
| `KC_IMAGE` | ✓ | ✗ | n/a | transport always uses compiled-in default |
| `KC_BASE_IMAGE` | ✓ | ✗ | n/a | transport always uses compiled-in default |
| `KIRO_API_KEY` | ✓ (via cfg.kiro_api_key) | ✗ | n/a | see Decision 3 below |
| `TRANSPORT_DATA_DIR` | ✓ | ✗ | `/data` mount exists | effectively pinned to `/data`; see Decision 4 |
| `GA_RATE_LIMIT_DASHBOARD_AUTH` | ✗ (bespoke in auth.py) | ✗ | n/a | setting ignored; see Decision 5 |
| `GA_FILE_SECRET` | ✗ (bespoke in files.py) | ✗ | n/a | by design; see Decision 6 |
| `GA_ORDERS_DIR` | ✓ | ✓ | ✗ | env set but path unreachable inside container |
| `GA_TLS_CERTFILE` | ✓ | ✓ | ✗ | env set but path unreachable inside container |
| `GA_TLS_KEYFILE` | ✓ | ✓ | ✗ | env set but path unreachable inside container |
| `PORT` (transport) | ✓ | hard-coded `"64057"` | n/a | changing `PORT` does not change transport listen port |

Additionally two code-level correctness issues from the quality reviewer:

- `GA_MAX_ACTIVE_CREWS` negative: the `> 0` guard means any negative value disables the
  limit, identical to `0`, but this is undocumented.
- `_TASK_TIMESTAMP_TTL_SECS` floor: the comment in `lifecycle.py` says "Both TTLs floor
  at one hour" but the code has no floor; setting `GA_TASK_TIMESTAMP_TTL_SECS=1` works,
  and the comment is misleading.

## Goals / Non-Goals

**Goals:**
- Wire `GA_PREWARM_ENABLED`, `GA_PREWARM_TTL_SECS`, `KC_IMAGE`, `KC_BASE_IMAGE` into
  compose.yml so operators can control them from `ghostship.conf`.
- Add conditional volume mounts for `GA_ORDERS_DIR` and `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`
  so those paths are actually reachable inside the container when set.
- Add `GA_RATE_LIMIT_DASHBOARD_AUTH` to compose.yml (it is read from env by `auth.py`).
- Clarify `PORT` semantics: the transport's internal listen port is intentionally
  decoupled from the host-side `PORT`; document this clearly.
- Fix `GA_MAX_ACTIVE_CREWS` negative-value semantics by aligning documentation with
  actual code behaviour (negative = disable, same as 0).
- Fix the `_TASK_TIMESTAMP_TTL_SECS` comment to match reality (no floor is enforced).
- Update `docs/configuration.md` and `config/ghostship.conf.example` to match resolved
  state.

**Non-Goals:**
- Making the transport's listen port configurable via `PORT` (see Decision 1).
- Adding a floor to `_TASK_TIMESTAMP_TTL_SECS` in code (see Decision 7).
- Removing env vars from `config.py` (all entries stay; this change only wires them through
  install.sh and documents them correctly).
- Auditing `docs/forks.md`, `docs/agents.md`, `docs/portal.md`, `docs/auth.md` (proposal
  marks these as out of scope for first pass).

## Decisions

### Decision 1 — PORT does not control the transport's internal listen port

**Decision:** Keep `PORT: "64057"` hard-coded in the compose `environment:` block. Do
not make the transport's container-internal listen port configurable via `PORT`.

**Rationale:** Caddy's upstream dial strings (`ga-transport:64057`) are baked into the
generated `initial-config.json`. Making the transport listen on a different internal port
would require either (a) regenerating the Caddy config every time `PORT` changes, or (b)
adding a separate env var (`TRANSPORT_INTERNAL_PORT`). Both add complexity for no operator
benefit — operators never need to change the internal container-to-container port. `PORT`
is already documented as the *host* port Caddy listens on.

**What changes:** `docs/configuration.md` gets a note clarifying that `PORT` controls the
Caddy host port only; the transport always listens on 64057 inside its container. The table
entry in `ghostship.conf.example` already says this but the docs table needs the same
clarification.

**Alternative considered:** Add `TRANSPORT_PORT` var and thread it through both compose and
the Caddy upstream string. Rejected: unnecessary complexity, no real use case.

### Decision 2 — GA_ORDERS_DIR and GA_TLS_CERTFILE/KEYFILE get conditional volume mounts

**Decision:** When `GA_ORDERS_DIR` is set in `ghostship.conf`, `install.sh` adds a
`- <host_path>:/mnt/orders:ro` volume entry to the compose `ga-transport` service and
rewrites the env var value to the container path `/mnt/orders`. Similarly, when
`GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are set, mount their parent directory (or each
file individually) read-only and rewrite the env var paths to the container-side paths.

**TLS mount approach:** Mount the directory containing the cert/key pair as
`/mnt/tls` (read-only). Set `GA_TLS_CERTFILE=/mnt/tls/<cert_basename>` and
`GA_TLS_KEYFILE=/mnt/tls/<key_basename>` inside the container. Require cert and key to
live in the same directory; if they don't, error at install time with a clear message.

**Rationale:** The alternative (passing host paths verbatim) can never work from inside a
container without a mount. Volume mounts are the standard Compose pattern. Rewriting to
container paths keeps the transport's config.py paths self-consistent.

**Alternative considered:** Mount each file individually (e.g. `/mnt/tls-cert`,
`/mnt/tls-key`). Rejected: more volume entries for minimal benefit; same-directory
requirement is reasonable for a cert/key pair.

### Decision 3 — KIRO_API_KEY is already handled correctly; no compose change

**Decision:** Do not add `KIRO_API_KEY` to the compose `environment:` block.

**Rationale:** `server.py` reads `cfg.kiro_api_key` (from `Config.from_env()`), and
`install.sh` already handles KIRO_API_KEY separately: it stores the value as a Podman
secret (`ga-kiro-api-key`), which is mounted into the container at
`/run/secrets/ga-kiro-api-key`, and `server.py` reads it from there. Adding it as a
plain env var in compose would expose the key in `compose.yml` (which is chmod 600 but
is still a secret in plaintext). The current pattern is correct and intentional.

**What changes:** Confirm documentation in `ghostship.conf.example` is accurate (it is).

### Decision 4 — TRANSPORT_DATA_DIR stays absent from compose env; document as internal

**Decision:** Do not add `TRANSPORT_DATA_DIR` to the compose `environment:` block.

**Rationale:** The transport container always mounts `DATA_DIR` from the host as `/data`.
The `TRANSPORT_DATA_DIR` env var would only have effect if the operator also changed the
volume mount target — which would require a custom compose.yml anyway. Adding it to the
generated compose as `TRANSPORT_DATA_DIR: "/data"` adds noise without enabling anything.
`ghostship.conf.example` already notes it; no operator action needed.

**What changes:** `docs/configuration.md` adds a note that this var is effectively pinned
to `/data` in the standard install; `ghostship.conf.example` is already accurate.

### Decision 5 — GA_RATE_LIMIT_DASHBOARD_AUTH added to compose.yml

**Decision:** Add `GA_RATE_LIMIT_DASHBOARD_AUTH: "${GA_RATE_LIMIT_DASHBOARD_AUTH:-600:60}"`
to the compose `environment:` block alongside the other `GA_RATE_LIMIT_*` entries.

**Rationale:** `auth.py` reads it from the environment using the same `_RATE_LIMIT_DEFAULTS`
pattern as all other rate-limit vars. It is documented in `docs/configuration.md` and
`ghostship.conf.example` but silently had no effect. The fix is one line.

**What changes:** compose template in `install.sh` gains one env entry. Also add it to
`ghostship.conf.example` (currently missing) with the same comment style as the other
`GA_RATE_LIMIT_*` vars.

### Decision 6 — GA_FILE_SECRET stays absent from compose; document the reason

**Decision:** Do not add `GA_FILE_SECRET` to compose.yml.

**Rationale:** `ghostship.conf.example` already documents this explicitly: "install.sh
does not pass an override. The stored secret survives transport restarts." The file secret
is auto-generated and persisted in `DATA_DIR` on first start; there is no operator use
case for injecting a custom value via compose. The current behaviour is intentional.

**What changes:** `docs/configuration.md` adds a sentence confirming this is by design
(currently the table entry does not mention it).

### Decision 7 — Fix the _TASK_TIMESTAMP_TTL_SECS comment; no code floor added

**Decision:** Remove the "floor at one hour" claim from the `lifecycle.py` comment. Do
not add an actual floor to the code.

**Rationale:** A floor was never implemented (TRN-156 did not add one). The comment is
simply wrong. Adding a floor would be a behaviour change and could interfere with tests
that deliberately use small TTL values. Fixing the comment is sufficient and safe.

**What changes:** One-line comment fix in `transport/lifecycle.py`.

### Decision 8 — GA_PREWARM_ENABLED and GA_PREWARM_TTL_SECS added to compose.yml

**Decision:** Add both prewarm vars to the compose `environment:` block.

**Rationale:** They are fully wired in `config.py` and used at runtime. The only gap is
the compose template omitting them. Both are already documented in `ghostship.conf.example`.

**What changes:** Two lines added to the compose env template in `install.sh`.

### Decision 9 — KC_IMAGE and KC_BASE_IMAGE added to compose.yml

**Decision:** Add both image vars to the compose `environment:` block.

**Rationale:** Operators legitimately override `KC_IMAGE` to use a custom crew image and
`KC_BASE_IMAGE` to pin the base image version. Both are documented in `ghostship.conf.example`
but currently silently ignored at runtime. `KC_IMAGE` is used as a `--build-arg` during
image build and should also be injected into the container so the transport knows which
image to use when spawning crews.

**What changes:** Two lines added to compose env template. `docs/configuration.md` and
`ghostship.conf.example` entries already exist and are accurate.

### Decision 10 — GA_MAX_ACTIVE_CREWS negative value: document as disable

**Decision:** Document negative values as equivalent to `0` (disables the limit). Do not
add validation to reject negative values.

**Rationale:** The current code uses `if GA_MAX_ACTIVE_CREWS > 0:` — both `0` and any
negative value skip the check. The `ghostship.conf.example` already says "Set to 0 to
disable" but does not mention negative values. The safer fix is documentation: operators
using negative values should use `0` instead. Rejecting negatives at validation time would
be a breaking change for anyone who currently uses a negative value intentionally.

**What changes:** `docs/configuration.md` table entry and `ghostship.conf.example` comment
are updated to note that values `≤ 0` all disable the limit.

## Risks / Trade-offs

**Volume mount for GA_ORDERS_DIR may break installs that set the var to a non-existent path →**
Mitigation: `install.sh` already warns if the path is set but missing (runtime). The install
step should warn at install time too (before writing compose.yml) so the operator is
notified. Add a `[[ -d "$GA_ORDERS_DIR" ]]` check in `install.sh` that prints a warning
but does not abort (the runtime warning already handles the absent-at-startup case).

**TLS cert/key in same directory requirement →**
Mitigation: This is a new constraint not previously enforced. `install.sh` must check and
error clearly if they differ. Operators with certs split across directories will need to
copy or symlink one file. Document this in `ghostship.conf.example`.

**KC_IMAGE in compose.yml vs as a build-arg →**
`KC_IMAGE` is currently only used as a `--build-arg` at image build time, and `install.sh`
already passes it there. Adding it to the compose env block means the transport will pick
it up at runtime too — this is correct (that's what `Config.from_env()` reads for
`kc_image`). No double-effect risk since the two uses are independent.

**GA_RATE_LIMIT_DASHBOARD_AUTH was silently 600:60 for all existing installs →**
Adding it to compose.yml means a re-install will now write the env var explicitly. If an
operator had a `GA_RATE_LIMIT_DASHBOARD_AUTH` value in `ghostship.conf` it was previously
ignored; after the fix it will take effect. Low risk: the default value is unchanged
(600:60), so reinstalling with no explicit override is a no-op.

## Migration Plan

All changes take effect after `./scripts/install.sh` is re-run (compose.yml is
regenerated). No data migrations, no container image changes, no schema changes.

1. Run `./scripts/install.sh` to regenerate `compose.yml`.
2. Restart the stack: `podman compose -f $DATA_DIR/compose.yml up -d`.
3. Operators who previously set `GA_ORDERS_DIR` or `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`
   should verify paths are correct and accessible before restarting.
4. No rollback path needed — the compose.yml can be regenerated at any time from the
   installed `ghostship.conf`.
