# Verification

## Runtime wiring and migration

Generated crew fallback uses supported `agent.model`; empty resolution writes `auto`. The patch script removes legacy `agent.default_model` only during model updates. Legacy/nonlegacy migration tests cover a new value, clear-to-auto, idempotence and unrelated state preservation. No operator configuration or credentials were changed.

## Consumer integration

Command: `.venv/bin/python tests/integration/test_model_defaults.py --connection <local-podman-connection>`.

Image tested: `sha256:fa1a1e63670d8bdfcbd77eac02dba72b9ecd6471432aa632ef9ebb1bcfbcb5b7`, built from the pinned KiroCrew base image. The disposable container receives the current host-generated lifecycle payloads and current patch scripts; no deployment is required to exercise the changed producer against the actual downstream consumer.

27 cases passed (nine for each kiro/claude/codex namespace): backend-over-global, global fallback, persona precedence, dispatch precedence, backend override, dispatch-over-override, empty defaults, persona auto inheritance, and clearing an earlier fallback. Every case loads generated configuration via pinned KiroCrew and uses its model resolver/factory selection, tests idempotent patching and preservation of dummy operator/credential canaries, and removes the obsolete field. The container has no network and no provider calls or real credentials. These checks prove requested-model resolution, not subscription entitlements or provider availability. Namespace translation remains upstream behavior.

## Checks

- `.venv/bin/python -m pytest tests/unit/test_lifecycle.py tests/unit/test_model_default_migration.py tests/unit/test_container_scripts.py tests/unit/test_yaml_config.py tests/unit/test_config.py -q`: 279 passed.
- Final migration guard adjustment: migration suite 3 passed and all 27 consumer cases re-ran successfully.
- All seven built-in model settings (global fallback and per-backend default/override pairs) are empty in both runtime and installer defaults.
- `git diff --check`: passed.
- `openspec validate trn-313-backend-model-default-wiring`: passed with the expected warning for convention-required `ticket` metadata.

No deployment, model pin, persona rewrite, actual-model reporting API change or harness rejection/fallback retry policy was introduced. A separately approved rollout and fresh session are needed to observe changes in a running instance.

## Approved local deployment

User explicitly approved manual installation after implementation. `ghostship install --config config/ghostship.yaml` completed successfully; independent health check returned HTTP 200. A fresh default-backend crew generated `agent.acp_backend=codex` and `agent.model=gpt-6-luna`, with no obsolete `agent.default_model` field. The operator-selected local value was preserved; no concrete model was added to shipped defaults. Initial live smoke execution was deferred by the upstream memory admission guard while startup-restored crews consumed available memory. No resource guard was lowered. Actual model/result verification is pending that task’s completion.

## Live smoke outcome

Idle-stop reclaimed capacity without lowering memory controls. The live Codex task completed with MODEL_DEFAULT_WIRING_OK. Its actual session turn_context records model gpt-6-astra and effort low. The upstream log confirms the higher-precedence persona pin claude-haiku-5.5 was refused, leaving the session on the harness default rather than retrying the configured fallback. The advertised model list contains gpt-5.6-luna and does not contain gpt-6-luna. Thus supported-field delivery is verified on the deployed instance, but this live task does not demonstrate execution on the configured Luna 6 model. The persona and entitlement/fallback-policy limitations are unchanged, as scoped in the design. The disposable smoke crew is retained for inspection; no cleanup or model substitution was performed.

## Backend-neutral persona live test

User requested removing shipped persona model pins and retesting inheritance. All six shipped persona JSON files now omit model; operator overrides also apply to omitted/auto model fields. Updated verification: 306 affected unit tests passed, and 30 pinned-consumer cases passed, including override of unpinned personas for each backend namespace.

Installed the updated files locally with the existing operator-selected gpt-6-luna default unchanged. A fresh crew’s Ghost persona was independently inspected and has no model field. Live task completed with UNPINNED_MODEL_OK. Upstream now logs the requested model as gpt-6-luna rather than the removed foreign persona model, proving backend-default inheritance. It explicitly refuses gpt-6-luna as unavailable and leaves the session on the harness default. Session metadata confirms gpt-6-astra / low actually ran. The advertised Luna model is gpt-5.6-luna. No substitute model was configured without the operator’s choice.

To free memory for the test, only earlier completed smoke-test containers were stopped; no workspaces were deleted. The current smoke crew remains available for inspection.

## Dashboard-led toolchain diagnosis

Launched a fresh crew with dashboard enabled and inspected KiroCrew through the browser UI. Initial JavaScript startup failed because a proxied asset contained compressed bytes without a Content-Encoding header. Requesting identity encoding and disabling that browser’s cache allowed UI startup; this was a diagnostic workaround, not a deployed proxy fix.

UI model settings show the configured gpt-6-luna fallback. After a minimal chat turn, the transcript reports gpt-6-astra[low] and explicitly warns that Codex adapter 1.12.0 is outside KiroCrew’s tested range 2.x. The model picker contains only the old advertised catalog.

Through the dashboard terminal, confirmed active CLI 0.154.0. Installed adapter 2.5.0 into a temporary directory only; its dependency supplies CLI 0.165.0. Using the same saved login, the temporary app-server model/list advertised gpt-6-luna (plus newer Sol/Terra models). An ephemeral read-only direct CLI request explicitly selecting gpt-6-luna completed with LUNA6_AVAILABLE_OK and no stderr. This demonstrates account/service access to Luna 6 and identifies the old toolchain/catalog as the selection blocker. Earlier unavailable-model statements apply to the old advertised list, not global model existence or verified account entitlement.

The active adapter and repo toolchain pin were not upgraded during this UI diagnosis. Next repair: update the pinned adapter to the tested 2.x series and verify a fresh KiroCrew session, while preserving gpt-6-luna as the operator’s requested model.

## Local adapter upgrade and final KiroCrew verification

User authorized completion locally. Source now pins codex-acp 2.5.0 and continues exposing its own bundled CLI. Rebuilt spec-ops image reports adapter 2.5.0 and codex-cli 0.165.0. Image ID: 14d866e66365e514875daf4c7ecffc2a9d63db896ab393c86747057cb1d6653f. The original operator-selected gpt-6-luna configuration and saved credentials were preserved.

Verification: 272 affected unit cases plus 119 configuration cases passed (391 total); all 30 disposable pinned-consumer cases passed on the rebuilt image. OpenSpec validation and git diff --check pass. The local installer rebuilt all images and restarted services, but returned nonzero during its health-check stage while retained crews were being restored; independent subsequent /health returned HTTP 200 and MCP calls succeeded. Completed smoke containers restored during startup were stopped reversibly to reclaim memory; no workspaces were deleted.

Launched a fresh default-backend spec-ops crew from the rebuilt image and dispatched Ghost without a model argument. The minimal no-tools request completed successfully with TRN313_LUNA_OK and no error. Independently read the Codex session JSONL turn_context: model=gpt-6-luna, effort=max. This is actual KiroCrew-dispatched execution, superseding the earlier temporary direct-CLI-only evidence. Fresh-crew fallback inheritance now works on the requested model. Existing crews remain bound to their original image; no automatic unavailable-model retry ladder was added. The dashboard compression issue diagnosed earlier remains a separate issue.
