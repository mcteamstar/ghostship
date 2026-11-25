# Tasks

## 1. Transport mailbox-subject endpoint

- [ ] 1.1 Implement a strict subject-only reader for all eight crew mailboxes, supporting Maildir and legacy mbox files for running and stopped crews; distinguish unreadable sources from empty mailboxes. Verify coverage for both formats, running/stopped crews, empty/unavailable mailboxes, and read-only behavior, with output containing subject strings only.
- [ ] 1.2 Expose `GET /internal/crews/{crew_id}/mail-subjects` through the TransportSecretMiddleware path handling and OpenAPI registry. Verify missing/invalid tokens return no mailbox data, unknown crews return 404, and successful responses contain only mailbox names and subject lists.

## 2. Radar proxy and operator view

- [ ] 2.1 Add `GET /api/crews/{crew_id}/mail-subjects` as a Radar proxy to Transport. Verify token forwarding, response shape, and safe unavailable responses when Transport or the mailbox source fails.
- [ ] 2.2 Add a lazily loaded subject section to expanded crew details, grouped by mailbox. Escape subject text and render clear empty and unavailable states; verify client tests cover those states and that mailbox reads do not run during fleet polling.
- [ ] 2.3 Update `docs/radar.md` with the mailbox-subject view, endpoint, response shape, and Portal session requirement. Verify examples expose only mailbox names and subject strings.

## 3. Session and contract integration

- [ ] 3.1 Verify the new browser route remains behind the existing Caddy Portal session gate and the internal route requires the Transport secret; run focused Caddy, Transport, and Radar tests and confirm bodies and message metadata never appear in the browser response.
