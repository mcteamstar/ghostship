# Design

## Context

See proposal.md. Runtime reads GA_TRUSTED_PROXY_CIDR, checks the immediate ASGI peer against configured CIDRs, and uses the first forwarded address only for trusted peers.

## Goals / Non-Goals

**Goals:**
- Define the security precondition for trusting forwarded client addresses.
- Make examples and configuration text match the implementation.

**Non-Goals:**
- Change rate-limit keying, CIDR parsing, or forwarded-header behavior.

## Decisions

- Update the full existing Composite caller-identity requirement rather than adding a parallel requirement, so old last-hop semantics cannot remain normative.
- Use first-hop behavior only after trusted-peer validation; state fallback and unset behavior explicitly.
- Keep API-key hashing behavior and existing bucket scenarios intact.

## Risks / Trade-offs

- [Docs cause operators to trust an overly broad proxy range] → Keep examples narrow and warn that trusted peers can influence the forwarded address.
- [Spec drifts from middleware code again] → Add focused tests for trusted, untrusted, and missing-header cases if existing tests do not cover them.
