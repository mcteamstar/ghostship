## 1. Template file (already done)

- [x] 1.1 Create `academy/orders/free-will.md` with front matter `aliases: ["free",
  "willy"]`, `<message>` placeholder body, standard `{{RAVEN_GATEWAY_ORIENTATION}}`,
  `{{RAVEN_STORE_RESOLUTION}}`, `{{RAVEN_SELF_CANCEL}}` placeholders, and
  intent/idempotency + memory-pressure protocol.

## 2. Transport — add `<message>` placeholder substitution

- [x] 2.1 In `transport/captain.py`, extend `_resolve_order_template()` to handle a
  `<message>` placeholder: accept a new `message: str | None` parameter. After all
  `<change*>` substitutions, if `<message>` appears in the body, substitute it with
  the `message` value. If `<message>` is in the body and `message` is None, raise
  `ValueError(f"Template {template!r} requires message")`.
- [x] 2.2 Update all call sites of `_resolve_order_template()` in `tools.py` and
  `captain.py` to pass `message=message` (or `message=None` where not applicable).
  Also relaxed the `has_message == has_template` mutual exclusion in
  `captain_engine.py` to allow both when template accepts `<message>`.
- [x] 2.3 Add a unit test covering `<message>` substitution in
  `tests/unit/test_captain.py` (or equivalent).

## 3. Transport docstring update

- [x] 3.1 In `transport/tools.py`, find the `captain` tool docstring. Add `free-will`
  (aliases: `free`, `willy`) to the list of available templates alongside `sdd` and
  `indy`. Describe it as: the open-ended autonomous template — executes a freeform
  standing order with full agent autonomy; self-cancels on completion.

## 4. Skill update

- [x] 4.1 In `.claude-plugin/skills/ghostship-command/SKILL.md`, find the section
  describing Captain templates. Add `free-will` / `willy` as the third built-in
  template. Example wording: "`free-will` (alias: `willy`) — open-ended autonomous
  captaincy; executes the `message` instruction with full agent autonomy. Use for
  any task that doesn't need SDD structure."

## 5. Verification

- [x] 5.1 Confirm `transport://orders` lists `free-will` with a non-empty description
  (check via `ghostship` CLI or MCP resource call).
- [x] 5.2 Run `bash scripts/run.sh --unit` — all tests pass.
