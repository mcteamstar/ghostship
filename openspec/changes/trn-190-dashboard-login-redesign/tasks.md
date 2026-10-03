## 1. Rewrite `handle_login_get` HTML in `transport/dashboard.py`

- [ ] 1.1 Update card width to 360px and improve label/field spacing
- [ ] 1.2 Replace green button (`#2d6a4f`) with Ghostship purple (`#7c3aed`), hover `#6d28d9`
- [ ] 1.3 Add `<div class="hero">` with ghost emoji and CSS float animation (`translateY ±6px`, `3s ease-in-out infinite`)
- [ ] 1.4 Add `@keyframes` for float animation and `@keyframes` for shake animation in the `<style>` block
- [ ] 1.5 Wrap the password input in a relative-positioned container; add `<button type="button">` with inline SVG eye icon for show/hide toggle
- [ ] 1.6 Add inline JS to toggle `input.type` between `password` and `text` on eye button click
- [ ] 1.7 Update failed-login JS: add `.shake` class to error paragraph on 401/403 response; remove class on `animationend` so it re-triggers on subsequent failures
- [ ] 1.8 Add `.shake` CSS class with `@keyframes shake` in the `<style>` block

## 2. Verify

- [ ] 2.1 Run existing tests — confirm no functional regressions (`pytest tests/unit/ -q`)
- [ ] 2.2 Manually load `GET /dashboard/login` in a browser and verify: ghost hero floats, button is purple, show/hide toggle works, shake fires on bad key
