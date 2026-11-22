## Context

The general limiter sits outside bearer auth. The separate bearer failure throttle already uses source IP.

## Decisions

- Preserve the existing source resolution and authenticated composite key. Select a token bucket only after validating the credential using the same rules as auth. Share validation logic and leave existing auth decisions and endpoint exemptions in place.
- Propose a 10,000-key cap per endpoint limiter. Sweep expired buckets across keys under the limiter lock using bounded work. At capacity, reject unseen keys with the existing 429 contract while honoring active buckets. Do not evict live buckets to admit new identities.
- Keep rate windows and per-endpoint limits unchanged. Treat state as local to each Transport process. The separate sign-in failure throttle is outside this change.

## Trade-offs

At saturation, new callers may receive 429 until a bucket expires. This preserves existing quotas and bounds memory.
