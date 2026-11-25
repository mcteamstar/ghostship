# Tasks

## 1. Transport mailbox-subject endpoint

- [x] 1.1 Implement a strict subject-only reader for all eight crew mailboxes, supporting Maildir and legacy mbox files for running and stopped crews. Treat a missing mailbox path (including Podman's archive path-not-found response for an unprovisioned `admiral`) as empty; fail the whole request on any other read error. Confirm a stopped crew's container exists before archive reads, treat a missing container as unavailable, and make `container_archive_get` raise a typed not-found error for HTTP 404. Order subjects newest first by Maildir filename timestamp (reverse file order for mbox), cap each mailbox at 50 subjects, and truncate subjects to 200 characters. Verify coverage for both formats, running/stopped crews, a stopped crew with no `admiral` mailbox, a registered crew whose container was removed, empty/unavailable mailboxes, ordering, caps, and read-only behavior, with output containing subject strings only.
- [x] 1.2 Expose `GET /internal/crews/{crew_id}/mail-subjects` through the TransportSecretMiddleware path handling and OpenAPI registry. Verify missing/invalid tokens return no mailbox data, unknown crews return 404, and successful responses contain only mailbox names and subject lists.

## 2. Radar proxy and operator view

- [x] 2.1 Add `GET /api/crews/{crew_id}/mail-subjects` as a Radar proxy to Transport. Verify token forwarding, response shape, and safe unavailable responses when Transport or the mailbox source fails.
- [x] 2.2 Add a lazily loaded subject section to expanded crew details, grouped by mailbox. Escape subject text and render clear empty and unavailable states; verify client tests cover those states and that mailbox reads do not run during fleet polling.
- [x] 2.3 Update `docs/radar.md` with the mailbox-subject view, endpoint, response shape, and Portal session requirement. Verify examples expose only mailbox names and subject strings.

## 3. Session and contract integration

- [x] 3.1 Verify the new browser route remains behind the existing Caddy Portal session gate and the internal route requires the Transport secret; run focused Caddy, Transport, and Radar tests and confirm bodies and message metadata never appear in the browser response.
