## 1. Narrow bare except Exception: pass

- [ ] 1.1 In `transport/podman.py`, audit all `except Exception: pass` blocks — list each method
- [ ] 1.2 `container_stop`, `container_remove` — narrow to `httpx2.HTTPStatusError` where `status_code in (404,)`; log WARNING + re-raise on anything else
- [ ] 1.3 `volume_create` — narrow to `httpx2.HTTPStatusError` where `status_code == 409`; remove misleading "# already exists" comment; propagate other errors
- [ ] 1.4 `volume_remove`, `secret_remove`, `network_disconnect`, `network_rm` — apply same pattern (404 tolerated, others logged + re-raised)
- [ ] 1.5 Worker cleanup block — narrow or log; don't silently swallow

## 2. Close httpx2 clients on exit

- [ ] 2.1 After the two module-level client instantiations, add `atexit.register(client.close)` for the sync client
- [ ] 2.2 Add a sync wrapper that calls `asyncio.run(async_client.aclose())` and register with `atexit` for the async client
- [ ] 2.3 Verify import: `import atexit` added if not already present

## 3. Fix container_exec response leak

- [ ] 3.1 In `container_exec`, replace bare `.content` access with `with client.send(req) as response: return response.content` (or equivalent context manager form)

## 4. Fix raw socket leaks

- [ ] 4.1 In `container_exec_pty_stdin` — wrap connect + HTTP upgrade block in `try/except: sock.close(); raise`
- [ ] 4.2 In `container_exec_stdin` — same pattern

## 5. Verification

- [ ] 5.1 `python3 -m py_compile transport/podman.py` — syntax clean
- [ ] 5.2 Run full unit suite — all pass
